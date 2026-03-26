from django.shortcuts import render
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone as dj_timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny

from .utils import get_client_ip

security_logger = logging.getLogger("gpp.fontend_log")# Create your views here.
class FrontEndLogging(APIView):
    
    permission_classes = [AllowAny]
    
    def frontend_log(self, request):
        log_data = request.data
        remote_adress = get_client_ip(request)
        
        security_logger.info("FROONTEND_LOG_ERR: {remote_adress} - {log_data}")
        
        return Response({"status": "ok"})