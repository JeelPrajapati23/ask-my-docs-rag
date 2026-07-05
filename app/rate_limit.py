from slowapi import Limiter


def get_client_ip(request) -> str:
    """
    request.client.host is Azure Container Apps' own internal ingress IP
    (RFC 6598 100.64.0.0/10) for every request, not the visitor's — Container
    Apps terminates the connection and re-originates it before it reaches this
    process. X-Forwarded-For carries the real chain (browser, then Vercel's
    proxy, then Azure's ingress); the leftmost entry is the original client.
    This is spoofable by a request sent directly to the Azure FQDN (bypassing
    Vercel) with a forged header — acceptable for this app's low-stakes
    rate-limit/audit-log attribution; locking that down would mean restricting
    direct public access to the Container App instead.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_client_ip)
