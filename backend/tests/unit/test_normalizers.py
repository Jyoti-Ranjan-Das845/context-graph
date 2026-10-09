"""Each normalizer against small synthetic records shaped like the real PyAirbyte output."""

import base64

from context_graph.domain import EdgeKind, NodeKind
from context_graph.domain import keys
from context_graph.sources.github.normalizer import GitHubNormalizer
from context_graph.sources.gmail.normalizer import GmailNormalizer
from context_graph.sources.jira.normalizer import JiraNormalizer
from context_graph.sources.linear.normalizer import LinearNormalizer
from context_graph.sources.notion.normalizer import NotionNormalizer
from context_graph.sources.slack.normalizer import SlackNormalizer

USER = {"login": "dev1", "id": 7, "type": "User"}


def by_id(batch):
    return {i.id: i for i in batch.items}


def test_github_splits_prs_from_issues_and_links_comments():
    records = {
        "issues": [
            {"repository": "acme/pay", "number": 1, "title": "Bug", "body": "x", "html_url": "https://github.com/acme/pay/issues/1", "user": USER},
            {"repository": "acme/pay", "number": 2, "title": "Fix", "pull_request": {"url": "u"}, "user": USER},
        ],
        "pull_requests": [
            {"repository": "acme/pay", "number": 2, "title": "Fix it", "body": "Fixes #1", "html_url": "https://github.com/acme/pay/pull/2", "user": USER, "head": {"ref": "fix"}, "base": {"ref": "main"}},
        ],
        "comments": [
            {"repository": "acme/pay", "id": 11, "body": "looks good", "issue_url": "https://api.github.com/repos/acme/pay/issues/2", "user": USER},
        ],
        "commits": [
            {"repository": "acme/pay", "sha": "abcdef1234", "html_url": "https://github.com/acme/pay/commit/abcdef1234",
             "commit": {"message": "Add retry\n\nbody", "author": {"name": "Dev One", "email": "dev@acme.io", "date": "2026-10-08T19:05:53Z"}},
             "author": {"login": "dev1", "id": 7}},
        ],
    }
    batch = GitHubNormalizer().normalize(records)
    items = by_id(batch)
    assert "github:issue:acme/pay#2" not in items  # PRs are not double counted as issues
    pr = items["github:pull_request:acme/pay#2"]
    assert keys.github_number("acme", "pay", 2) in pr.keys and pr.props["head"] == "fix"
    comment = items["github:comment:11"]
    assert comment.relations[0].target == "github:pull_request:acme/pay#2"
    assert items["github:repository:acme/pay"].kind is NodeKind.REPOSITORY
    commit_person = next(p for p in batch.people if p.emails)
    assert commit_person.emails == {"dev@acme.io"} and commit_person.handles == {"dev1"}


def test_linear_resolves_identifiers_for_comments_and_skips_app_users():
    records = {
        "issues": [{"id": "u-1", "identifier": "ENG-5", "title": "Dup charges", "description": "see DEMO-1", "url": "https://linear.app/ws/issue/ENG-5/dup", "creatorid": "p1"}],
        "comments": [{"id": "c1", "body": "PR is up", "issueid": "u-1", "userid": "p1"}],
        "users": [
            {"id": "p1", "name": "Dev One", "displayname": "dev", "email": "dev@acme.io"},
            {"id": "bot", "name": "Linear", "email": "linear-123@linear.linear.app"},
        ],
    }
    batch = LinearNormalizer().normalize(records)
    items = by_id(batch)
    assert keys.issue("ENG-5") in items["linear:issue:ENG-5"].keys
    assert items["linear:comment:c1"].relations[0].target == "linear:issue:ENG-5"
    assert [p.native_id for p in batch.people] == ["p1"]


def test_jira_flattens_adf_and_skips_app_accounts():
    issue = {
        "id": "10010", "key": "DEMO-1", "projectkey": "DEMO",
        "fields": {
            "summary": "Customer reports duplicate charges",
            "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "See ENG-5"}]}]},
            "reporter": {"accountId": "a1", "emailAddress": "dev@acme.io", "displayName": "Dev One"},
            "status": {"name": "In Progress"},
        },
    }
    users = [{"accountid": "a1", "accounttype": "atlassian", "displayname": "Dev One"}, {"accountid": "bot", "accounttype": "app"}]
    batch = JiraNormalizer(domain="acme.atlassian.net").normalize({"issues": [issue], "users": users, "projects": [{"key": "DEMO", "name": "Demo"}]})
    item = by_id(batch)["jira:issue:DEMO-1"]
    assert item.body == "See ENG-5" and item.url == "https://acme.atlassian.net/browse/DEMO-1"
    assert item.props["status"] == "In Progress"
    assert {p.native_id for p in batch.people} == {"a1"}


def test_notion_assembles_page_text_in_order_including_nested_blocks():
    page_native = "01234567-89ab-cdef-0123-456789abcdef"
    def block(bid, parent, seq, kind, content, children=False, parent_type="page_id"):
        return {"id": bid, "type": kind, "has_children": children, "parent": {"type": parent_type, parent_type: parent, "sequence_number": seq},
                kind: {"rich_text": [{"plain_text": content}]}}
    records = {
        "pages": [{"id": page_native, "url": "https://app.notion.com/p/x-0123456789abcdef0123456789abcdef",
                   "properties": [{"name": "Name", "value": {"type": "title", "title": [{"plain_text": "Payments retry design"}]}}]}],
        "blocks": [
            block("b2", page_native, 1, "paragraph", "second"),
            block("b1", page_native, 0, "heading_2", "Problem", children=True),
            block("b1a", "b1", 0, "bulleted_list_item", "nested", parent_type="block_id"),
        ],
        "users": [{"id": "u1", "type": "person", "name": "Dev One", "person": {"email": "dev@acme.io"}}, {"id": "bot", "type": "bot"}],
    }
    batch = NotionNormalizer().normalize(records)
    page = batch.items[0]
    assert page.title == "Payments retry design"
    assert page.body.splitlines() == ["## Problem", "  - nested", "second"]
    assert keys.notion_page(page_native) in page.keys
    assert len(batch.people) == 1


def test_slack_dedupes_threads_skips_joins_and_links_replies():
    root = {"channel_id": "C1", "ts": "100.1", "thread_ts": "100.1", "user": "U1", "text": "Heads up <@U1>", "reply_count": 1}
    reply = {"channel_id": "C1", "ts": "100.2", "thread_ts": "100.1", "user": "U1", "text": "Root cause found"}
    join = {"channel_id": "C1", "ts": "99.0", "user": "U1", "subtype": "channel_join", "text": "joined"}
    records = {
        "channels": [{"id": "C1", "name": "payments", "context_team_id": "T1"}],
        "channel_messages": [root, join],
        "threads": [root, reply],
        "users": [{"id": "U1", "real_name": "Dev One", "name": "dev", "profile": {"real_name": "Dev One"}}, {"id": "B1", "is_bot": True}],
    }
    batch = SlackNormalizer().normalize(records)
    messages = [i for i in batch.items if i.kind is NodeKind.MESSAGE]
    assert [m.id for m in messages] == ["slack:message:C1:100.1", "slack:message:C1:100.2"]
    assert messages[0].body == "Heads up @Dev One"
    assert any(r.kind is EdgeKind.REPLY_TO and r.target == "slack:message:C1:100.1" for r in messages[1].relations)
    channel = next(i for i in batch.items if i.kind is NodeKind.CHANNEL)
    assert keys.channel("payments") in channel.keys
    assert len(batch.people) == 1


def test_gmail_groups_threads_and_skips_promotions():
    def message(mid, subject, labels, ts):
        data = base64.urlsafe_b64encode(f"Body of {mid} mentions DEMO-1".encode()).decode()
        return {"id": mid, "threadid": "t1", "labelids": labels, "internaldate": ts,
                "payload": {"mimeType": "text/plain", "body": {"data": data},
                            "headers": [{"name": "Subject", "value": subject}, {"name": "From", "value": "Maya <maya@acme.io>"}, {"name": "To", "value": "dev@acme.io"}]}}
    records = {"messages_details": [
        message("m1", "Customers charged twice", ["INBOX"], "1791487063000"),
        message("m2", "Re: Customers charged twice", ["INBOX"], "1791487088000"),
        message("m3", "Sale!", ["CATEGORY_PROMOTIONS"], "1791487099000") | {"threadid": "t2"},
    ]}
    batch = GmailNormalizer(skip_labels={"CATEGORY_PROMOTIONS"}).normalize(records)
    items = by_id(batch)
    thread = items["gmail:email_thread:t1"]
    assert thread.title == "Customers charged twice" and keys.title("Customers charged twice") in thread.keys
    assert "gmail:email:m3" not in items
    assert items["gmail:email:m2"].relations[0].target == thread.id
    assert {p.native_id for p in batch.people} == {"maya@acme.io", "dev@acme.io"}
