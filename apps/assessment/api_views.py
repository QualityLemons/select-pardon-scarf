import json
import sqlite3

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.assessment.scorer import score_attempt
from apps.assessment.reviewer import generate_review

from .models import AssessmentResult


def _cors(response):
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _json_response(data, status=200):
    response = JsonResponse(data, status=status)
    return _cors(response)


def _plec_db():
    con = sqlite3.connect(settings.PLEC_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _parse_json(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return None


@require_http_methods(["GET", "OPTIONS"])
def modules_list(request):
    if request.method == "OPTIONS":
        return _cors(JsonResponse({}))
    try:
        con = _plec_db()
        cur = con.cursor()
        cur.execute("""
            SELECT m.id, m.title, m.type, m.html_file, m.difficulty,
                   m.description, m.role_title, m.sort_order,
                   COUNT(ms.id) AS milestone_count
            FROM   modules m
            LEFT JOIN milestones ms ON ms.module_id = m.id
            GROUP BY m.id
            ORDER BY m.sort_order
        """)
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return _json_response({"modules": rows})
    except Exception as exc:
        return _json_response({"error": str(exc)}, status=500)


@require_http_methods(["GET", "OPTIONS"])
def tips_list(request, module_id):
    if request.method == "OPTIONS":
        return _cors(JsonResponse({}))
    try:
        con = _plec_db()
        cur = con.cursor()
        cur.execute(
            "SELECT sort_order, icon, variant, tip_text FROM supervisor_tips "
            "WHERE module_id = ? ORDER BY sort_order",
            (module_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        if not rows:
            return _json_response({"error": f"No tips found for module '{module_id}'"}, status=404)
        return _json_response({"module_id": module_id, "tips": rows})
    except Exception as exc:
        return _json_response({"error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def assess_submit(request):
    if request.method == "OPTIONS":
        return _cors(JsonResponse({}))

    body = _parse_json(request)
    if body is None:
        return _json_response({"error": "Invalid JSON"}, status=400)

    scoring = score_attempt(
        level_key=body.get("level", ""),
        milestones_done=body.get("milestones_done", []),
        scan_count=int(body.get("scan_count", 0)),
        elapsed_ms=int(body.get("elapsed_ms", 0)),
        bonus_flags=body.get("bonus_flags", {}),
    )
    review = generate_review(scoring)
    return _json_response({**scoring, **review})


@csrf_exempt
@require_http_methods(["GET", "POST", "OPTIONS"])
def results_list_or_create(request):
    if request.method == "OPTIONS":
        return _cors(JsonResponse({}))

    if request.method == "GET":
        qs = AssessmentResult.objects.all()
        if request.user.is_authenticated:
            qs = qs.filter(user=request.user)
        else:
            qs = qs.none()
        return _json_response({"results": [r.to_dict() for r in qs]})

    body = _parse_json(request)
    if body is None:
        return _json_response({"error": "Invalid JSON"}, status=400)

    required = (
        "level_key", "score", "grade", "tier_label",
        "milestones_done", "milestones_total", "efficiency_label",
    )
    for field in required:
        if field not in body:
            return _json_response({"error": f"Missing field: {field}"}, status=400)

    result = AssessmentResult.objects.create(
        user=request.user if request.user.is_authenticated else None,
        level_key=str(body["level_key"]),
        score=int(body["score"]),
        grade=str(body["grade"]),
        tier_label=str(body["tier_label"]),
        milestones_done=int(body["milestones_done"]),
        milestones_total=int(body["milestones_total"]),
        efficiency_label=str(body["efficiency_label"]),
        bonus_earned=int(body.get("bonus_earned", 0)),
        note=str(body.get("note", "")),
    )
    return _json_response(result.to_dict(), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE", "OPTIONS"])
def result_detail(request, result_id):
    if request.method == "OPTIONS":
        return _cors(JsonResponse({}))

    try:
        result = AssessmentResult.objects.get(pk=result_id)
    except AssessmentResult.DoesNotExist:
        return _json_response({"error": "Not found"}, status=404)

    if request.user.is_authenticated:
        if result.user_id and result.user_id != request.user.id:
            return _json_response({"error": "Forbidden"}, status=403)
    elif result.user_id:
        return _json_response({"error": "Login required"}, status=401)

    if request.method == "GET":
        return _json_response(result.to_dict())

    if request.method == "PUT":
        body = _parse_json(request)
        if body is None:
            return _json_response({"error": "Invalid JSON"}, status=400)
        result.note = str(body.get("note", ""))
        result.save()
        return _json_response(result.to_dict())

    result.delete()
    return _json_response({"deleted": result_id})


@login_required
@require_http_methods(["POST"])
def update_note(request, result_id):
    """Profile page note update (CSRF-protected form POST)."""
    from django.contrib import messages
    from django.shortcuts import redirect

    try:
        result = AssessmentResult.objects.get(pk=result_id, user=request.user)
    except AssessmentResult.DoesNotExist:
        messages.error(request, "Result not found.")
        return redirect("accounts:profile")

    result.note = request.POST.get("note", "")
    result.save()
    messages.success(request, "Reflection note saved.")
    return redirect("accounts:profile")
