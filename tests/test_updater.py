import requests

from app import updater


def http_error(code):
    resp = requests.Response(); resp.status_code = code
    return requests.HTTPError(response=resp)


def test_newer_equal_and_older():
    assert updater.check_for_update(lambda u: "1.2.0\n", "1.1.0").state == updater.AVAILABLE
    assert updater.check_for_update(lambda u: "1.1.0", "1.1.0").state == updater.UP_TO_DATE
    assert updater.check_for_update(lambda u: "1.0.9", "1.1.0").state == updater.UP_TO_DATE
    assert updater.check_for_update(lambda u: "1.10.0", "1.9.0").state == updater.AVAILABLE      # compara números, no texto


def test_network_failure_is_an_error_not_up_to_date():
    def boom(u): raise requests.ConnectionError("sin red")
    r = updater.check_for_update(boom, "1.1.0")
    assert r.state == updater.ERROR and "sin conexión" in r.message


def test_garbage_version_is_an_error():
    assert updater.check_for_update(lambda u: "<html>404</html>", "1.1.0").state == updater.ERROR


def test_server_error_is_an_error():
    def boom(u): raise http_error(500)
    assert updater.check_for_update(boom, "1.1.0").state == updater.ERROR


def test_missing_remote_version_falls_back_to_git(tmp_path):
    def nf(u): raise http_error(404)
    r = updater.check_for_update(nf, "1.1.0", root=tmp_path)             # sin .git
    assert r.state == updater.ERROR and "clon de Git" in r.message


def test_git_commit_comparison(tmp_path):
    import subprocess
    def g(*a, cwd=None): return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout
    origin, clone = tmp_path / "origin", tmp_path / "clone"
    g("init", "-q", "-b", "main", str(origin))
    (origin / "f").write_text("1"); g("-C", str(origin), "add", "."); g("-C", str(origin), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "1")
    g("clone", "-q", str(origin), str(clone))
    def nf(u): raise http_error(404)
    assert updater.check_for_update(nf, "1.1.0", root=clone).state == updater.UP_TO_DATE
    (origin / "f").write_text("2"); g("-C", str(origin), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "2")
    assert updater.check_for_update(nf, "1.1.0", root=clone).state == updater.AVAILABLE
    ok, msg = updater.apply_update(clone)
    assert ok and (clone / "f").read_text() == "2" or "pip" in msg


def test_apply_update_refuses_with_local_changes(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "x").write_text("sucio")
    ok, msg = updater.apply_update(tmp_path)
    assert not ok and "cambios locales" in msg
