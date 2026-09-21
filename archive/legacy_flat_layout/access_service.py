'''
Secure Data Access for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-10
'''

def check_scope(consent, request):
    requested = set(request.scope)
    allowed = set(consent.scope)
    return requested.issubset(allowed)


def authorize(
    state,
    proof,
    scope_valid
):
    if state != "ACTIVE":
        return False

    if not proof:
        return False

    if not scope_valid:
        return False

    return True