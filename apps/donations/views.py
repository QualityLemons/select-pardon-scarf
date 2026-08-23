from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

STRIPE_AVAILABLE = bool(settings.STRIPE_SECRET_KEY)


def _stripe_client():
    import stripe
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


@login_required
@require_POST
def create_checkout(request):
    """Create a Stripe Checkout Session for a one-time donation."""
    if not STRIPE_AVAILABLE:
        return JsonResponse({
            "error": "Stripe is not configured. Set STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY.",
        }, status=503)

    try:
        amount_gbp = int(request.POST.get("amount_gbp", "5"))
    except ValueError:
        return JsonResponse({"error": "Invalid amount"}, status=400)

    if amount_gbp < 1 or amount_gbp > 500:
        return JsonResponse({"error": "Amount must be between £1 and £500"}, status=400)

    amount_pence = amount_gbp * 100
    base = request.build_absolute_uri("/")[:-1]

    client = _stripe_client()
    session = client.checkout.sessions.create(
        params={
            "mode": "payment",
            "line_items": [{
                "price_data": {
                    "currency": "gbp",
                    "unit_amount": amount_pence,
                    "product_data": {
                        "name": "Support PLeC",
                        "description": "Donation to support free PLC engineering training",
                    },
                },
                "quantity": 1,
            }],
            "success_url": f"{base}/donate/success/?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{base}/donate/cancel/",
            "customer_email": request.user.email or None,
            "metadata": {
                "user_id": str(request.user.id),
                "username": request.user.username,
            },
        },
    )

    return JsonResponse({"checkout_url": session.url})


def success_view(request):
    session_id = request.GET.get("session_id", "")
    return render(request, "donations/success.html", {"session_id": session_id})


def cancel_view(request):
    return render(request, "donations/cancel.html")
