import json
import uuid
from django.core import signing
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.utils.decorators import method_decorator
from .models import Module, SupervisorTip, AssessmentResult
from .scorer import score_attempt
from .reviewer import generate_review

RESULT_TOKEN_SALT = 'plec.assessment.result_token'
RESULT_TOKEN_MAX_AGE = 600  # seconds — window in which a scored attempt may be persisted


def _cors_headers(response):
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


def cors_json(data, status=200):
    r = JsonResponse(data, status=status)
    return _cors_headers(r)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(View):
    """Report the current session's auth state to the static game pages.

    ensure_csrf_cookie guarantees the csrftoken cookie is set so the static
    header can POST to /logout/ with a valid CSRF token.
    """

    def get(self, request):
        if request.user.is_authenticated:
            return JsonResponse({
                'authenticated': True,
                'email': request.user.get_username(),
                'is_staff': request.user.is_staff,
            })
        return JsonResponse({'authenticated': False})


@method_decorator(csrf_exempt, name='dispatch')
class ModulesView(View):
    ...  # rest of the file unchanged

RESULT_TOKEN_SALT = 'plec.assessment.result_token'
RESULT_TOKEN_MAX_AGE = 600  # seconds — window in which a scored attempt may be persisted


def _cors_headers(response):
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


def cors_json(data, status=200):
    r = JsonResponse(data, status=status)
    return _cors_headers(r)

@method_decorator(ensure_csrf_cookie, name='dispatch')
class MeView(View):
    """Report the current session's auth state to the static game pages.

    ensure_csrf_cookie guarantees the csrftoken cookie is set so the static
    header can POST to /logout/ with a valid CSRF token.
    """

    def get(self, request):
        if request.user.is_authenticated:
            return JsonResponse({
                'authenticated': True,
                'email': request.user.get_username(),
                'is_staff': request.user.is_staff,
            })
        return JsonResponse({'authenticated': False})
@method_decorator(csrf_exempt, name='dispatch')
class ModulesView(View):
    def get(self, request):
        modules = (
            Module.objects
            .prefetch_related('milestones')
            .order_by('sort_order')
        )
        rows = []
        for m in modules:
            rows.append({
                'id': m.id,
                'title': m.title,
                'type': m.type,
                'html_file': m.html_file,
                'difficulty': m.difficulty,
                'description': m.description,
                'role_title': m.role_title,
                'sort_order': m.sort_order,
                'milestone_count': m.milestones.count(),
            })
        return cors_json({'modules': rows})

    def options(self, request):
        r = JsonResponse({})
        return _cors_headers(r)


@method_decorator(csrf_exempt, name='dispatch')
class TipsView(View):
    def get(self, request, module_id):
        tips = SupervisorTip.objects.filter(module_id=module_id).order_by('sort_order')
        if not tips.exists():
            return cors_json({'error': f"No tips found for module '{module_id}'"}, status=404)
        rows = [
            {
                'sort_order': t.sort_order,
                'icon': t.icon,
                'variant': t.variant,
                'tip_text': t.tip_text,
            }
            for t in tips
        ]
        return cors_json({'module_id': module_id, 'tips': rows})

    def options(self, request, module_id):
        r = JsonResponse({})
        return _cors_headers(r)


@method_decorator(csrf_exempt, name='dispatch')
class AssessView(View):
    def post(self, request):
        try:
            body = json.loads(request.body)
        except Exception:
            return cors_json({'error': 'Invalid JSON'}, status=400)

        level = body.get('level', '')
        milestones_done = body.get('milestones_done', [])
        scan_count = int(body.get('scan_count', 0))
        elapsed_ms = int(body.get('elapsed_ms', 0))
        bonus_flags = body.get('bonus_flags', {})

        scoring = score_attempt(
            level_key=level,
            milestones_done=milestones_done,
            scan_count=scan_count,
            elapsed_ms=elapsed_ms,
            bonus_flags=bonus_flags,
        )
        review = generate_review(scoring)
        result = {**scoring, **review}

        bonus_earned = sum(
            b['points'] for b in scoring.get('bonus_detail', []) if b.get('earned')
        )
        token_payload = {
            'nonce': uuid.uuid4().hex,
            'level_key': scoring['level_key'],
            'score': scoring['score'],
            'grade': scoring['grade'],
            'tier_label': review['tier_label'],
            'milestones_done': scoring['milestones_completed'],
            'milestones_total': scoring['milestones_total'],
            'efficiency_label': scoring['efficiency_label'],
            'bonus_earned': bonus_earned,
        }
        result['result_token'] = signing.dumps(token_payload, salt=RESULT_TOKEN_SALT)
        return cors_json(result)

    def options(self, request):
        r = JsonResponse({})
        return _cors_headers(r)


def _result_to_dict(r):
    return {
        'id': r.id,
        'level_key': r.level_key,
        'score': r.score,
        'grade': r.grade,
        'tier_label': r.tier_label,
        'milestones_done': r.milestones_done,
        'milestones_total': r.milestones_total,
        'efficiency_label': r.efficiency_label,
        'bonus_earned': r.bonus_earned,
        'note': r.note,
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else None,
    }


class ResultsListView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        results = AssessmentResult.objects.filter(user=request.user).order_by('-id')
        rows = [_result_to_dict(r) for r in results]
        return JsonResponse({'results': rows})

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        token = body.get('result_token')
        if not token:
            return JsonResponse({'error': 'Missing field: result_token'}, status=400)

        try:
            payload = signing.loads(
                token, salt=RESULT_TOKEN_SALT, max_age=RESULT_TOKEN_MAX_AGE
            )
        except signing.SignatureExpired:
            return JsonResponse({'error': 'result_token has expired'}, status=400)
        except signing.BadSignature:
            return JsonResponse({'error': 'Invalid result_token'}, status=400)

        nonce = payload.get('nonce')
        if not nonce:
            return JsonResponse({'error': 'Invalid result_token'}, status=400)

        if AssessmentResult.objects.filter(token_id=nonce).exists():
            return JsonResponse({'error': 'result_token has already been used'}, status=409)

        try:
            result = AssessmentResult.objects.create(
                user=request.user,
                level_key=str(payload['level_key']),
                score=int(payload['score']),
                grade=str(payload['grade']),
                tier_label=str(payload['tier_label']),
                milestones_done=int(payload['milestones_done']),
                milestones_total=int(payload['milestones_total']),
                efficiency_label=str(payload['efficiency_label']),
                bonus_earned=int(payload.get('bonus_earned', 0)),
                note=str(body.get('note', ''))[:2000],
                token_id=nonce,
            )
            return JsonResponse(_result_to_dict(result), status=201)
        except (KeyError, ValueError, TypeError):
            return JsonResponse({'error': 'Malformed result_token payload'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


class ResultDetailView(View):
    def get(self, request, rid):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        try:
            result = AssessmentResult.objects.get(pk=rid, user=request.user)
            return JsonResponse(_result_to_dict(result))
        except AssessmentResult.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)

    def put(self, request, rid):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        try:
            result = AssessmentResult.objects.get(pk=rid, user=request.user)
        except AssessmentResult.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)

        result.note = str(body.get('note', ''))
        result.save()
        return JsonResponse(_result_to_dict(result))

    def delete(self, request, rid):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        try:
            result = AssessmentResult.objects.get(pk=rid, user=request.user)
        except AssessmentResult.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)
        result.delete()
        return JsonResponse({'deleted': rid})
