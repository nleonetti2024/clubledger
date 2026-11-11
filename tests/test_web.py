"""End-to-end tests through the web interface (Flask test client)."""

import re

from conftest import sample


def csrf(client):
    html = client.get("/login").get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def login(client, name="Alex", role="member", pin=""):
    token = csrf(client)
    return client.post("/login", data={"name": name, "role": role, "pin": pin, "csrf_token": token})


def post(client, url, data):
    token = csrf(client)
    return client.post(url, data={**data, "csrf_token": token}, follow_redirects=False)


def submit(client, file="01_pizza_meeting.txt", amount="86.40", purpose="Meeting pizza"):
    return post(client, "/submit", {"purpose": purpose, "claimed_amount": amount,
                                    "receipt_text": sample(file)})


def test_health(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json["extractor"] == "rule-based-offline"


def test_pages_require_login(client):
    for url in ("/", "/submit", "/my", "/review", "/audit", "/export.csv", "/expenses/1"):
        r = client.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_wrong_treasurer_pin_refused_and_logged(client, app):
    r = login(client, "Mallory", "treasurer", "0000")
    assert r.status_code == 401
    assert client.get("/review").status_code == 302
    with app.app_context():
        events = app.get_conn().execute("SELECT action FROM audit_events").fetchall()
        assert [e[0] for e in events] == ["treasurer_login_failed"]


def test_post_without_csrf_token_is_refused(client):
    login(client)
    r = client.post("/submit", data={"purpose": "x", "claimed_amount": "1", "receipt_text": "y" * 20})
    assert r.status_code == 400


def test_security_headers_present(client):
    r = client.get("/login")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_member_cannot_open_treasurer_pages(client):
    login(client)
    for url in ("/review", "/audit", "/export.csv"):
        assert client.get(url).status_code == 403


def test_full_happy_path(client):
    # member submits
    login(client, "Alex")
    r = submit(client)
    assert r.status_code == 302
    detail_url = r.headers["Location"]
    page = client.get(detail_url).get_data(as_text=True)
    assert "Pending review" in page and "OWL CITY PIZZA CO." in page
    assert "Your decision" not in page  # members cannot decide

    # treasurer reviews and approves
    login(client, "Pat", "treasurer", "2468")
    queue = client.get("/review").get_data(as_text=True)
    assert "Meeting pizza" in queue
    expense_id = int(detail_url.rstrip("/").split("/")[-1])
    r = post(client, f"/expenses/{expense_id}/decide", {"decision": "approved", "reason": ""})
    assert r.status_code == 302

    # CSV export contains it
    csv_text = client.get("/export.csv").get_data(as_text=True)
    assert "OWL CITY PIZZA CO." in csv_text and "86.40" in csv_text and "Pat" in csv_text

    # member sees the decision
    login(client, "Alex")
    assert "Approved" in client.get("/my").get_data(as_text=True)


def test_flagged_expense_shows_policy_citation_and_needs_override(client):
    login(client, "Riley")
    r = submit(client, "04_alcohol.txt", "50.63", "Snacks for social")
    expense_id = int(r.headers["Location"].split("/")[-1])
    login(client, "Pat", "treasurer", "2468")
    page = client.get(f"/expenses/{expense_id}").get_data(as_text=True)
    assert "R2" in page and "§3.1" in page and "Prohibited item" in page
    r = post(client, f"/expenses/{expense_id}/decide", {"decision": "approved", "reason": "fine"})
    follow = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "justification" in follow and "Pending review" in follow


def test_members_cannot_see_each_others_expenses(client):
    login(client, "Alex")
    r = submit(client)
    url = r.headers["Location"]
    login(client, "Jordan")
    assert client.get(url).status_code == 404


def test_invalid_amount_shows_error_and_keeps_form(client):
    login(client)
    r = submit(client, amount="lots")
    assert r.status_code == 400
    assert "must be a number" in r.get_data(as_text=True)


def test_injection_receipt_shown_escaped_and_flagged(client):
    login(client, "Morgan")
    evil = sample("08_prompt_injection.txt") + "\n<script>alert(1)</script>"
    token = csrf(client)
    r = client.post("/submit", data={"purpose": "Expo tables", "claimed_amount": "111.30",
                                     "receipt_text": evil, "csrf_token": token})
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert "R10" in page and "Pending review" in page


def test_txt_upload_supported_and_other_types_refused(client):
    import io
    login(client)
    token = csrf(client)
    r = client.post("/submit", data={
        "purpose": "Banner", "claimed_amount": "57.78", "csrf_token": token,
        "receipt_file": (io.BytesIO(sample("06_printing_normal.txt").encode()), "r.txt")},
        content_type="multipart/form-data")
    assert r.status_code == 302
    token = csrf(client)
    r = client.post("/submit", data={
        "purpose": "Banner", "claimed_amount": "57.78", "csrf_token": token,
        "receipt_file": (io.BytesIO(b"%PDF"), "r.pdf")}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_csv_export_neutralises_formulas(client):
    login(client, "=HYPERLINK(evil)")
    r = submit(client, purpose="=1+1 pizza")
    expense_id = int(r.headers["Location"].split("/")[-1])
    login(client, "Pat", "treasurer", "2468")
    post(client, f"/expenses/{expense_id}/decide", {"decision": "approved"})
    csv_text = client.get("/export.csv").get_data(as_text=True)
    assert "'=HYPERLINK(evil)" in csv_text and "'=1+1 pizza" in csv_text
