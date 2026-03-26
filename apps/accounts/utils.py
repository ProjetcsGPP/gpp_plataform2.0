from django.http import JsonResponse
import logging
import json


logger = logging.getLogger(__name__)

def log_frontend_error(request_data):
    """
    Registra erros do frontend em log estruturado.
    Chamada pela view frontend_log().
    """
    try:
        error_data = json.loads(request_data)
        
        # Log estruturado com contexto
        log_entry = {
            'timestamp': error_data.get('timestamp'),
            'level': error_data.get('level', 'ERROR'),
            'message': error_data.get('message'),
            'context': error_data.get('context'),
            'url': error_data.get('url'),
            'user_agent': error_data.get('userAgent'),
            'ip': get_client_ip(request_data._request) if hasattr(request_data, '_request') else 'unknown'
        }
        
        logger.error(
            f"Frontend Error [{log_entry['context']}] {log_entry['message']}",
            extra={'data': log_entry}
        )
        
        return {'status': 'logged'}
    except Exception as e:
        logger.exception("Falha ao processar log frontend: %s", e)
        return {'status': 'error'}


def get_client_ip(request):
    """
    Retorna o IP real do cliente, considerando proxies reversos.
    Prioriza o primeiro IP do cabeçalho X-Forwarded-For.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
