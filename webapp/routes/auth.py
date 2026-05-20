from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from webapp.services import audit_log_service, auth_service

bp = Blueprint("auth", __name__)


@bp.get("/login")
def login_page():
    return render_template("login.html")


@bp.post("/login")
def login():
    user = auth_service.verify_login(
        request.form.get("username", ""),
        request.form.get("password", ""),
    )
    if not user:
        flash("登入失敗")
        return redirect(url_for("auth.login_page"))
    session.pop("dev_auto_login_suspended", None)
    session["user"] = user
    audit_log_service.append("auth.login", user["username"], {})
    return redirect(url_for("api_hosts.hosts_page"))


@bp.post("/logout")
def logout():
    username = (session.get("user") or {}).get("username", "anonymous")
    session.clear()
    session["dev_auto_login_suspended"] = True
    audit_log_service.append("auth.logout", username, {})
    return redirect(url_for("auth.login_page"))


@bp.get("/account/mfa")
def mfa_page():
    user = session.get("user")
    if not user:
        abort(401)
    return render_template("mfa.html", user=user)


@bp.post("/account/mfa")
def mfa_confirm():
    user = session.get("user")
    if not user:
        abort(401)
    auth_service.disable_mfa(user["username"])
    session["user"] = auth_service.get_user(user["username"])
    audit_log_service.append("auth.mfa.disable", user["username"], {})
    flash("OTP 驗證已停用")
    return redirect(url_for("auth.mfa_page"))
