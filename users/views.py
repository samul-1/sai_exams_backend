from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from rest_auth.registration.views import SocialLoginView
from rest_framework import generics

from . import models, serializers


class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter


google_login = GoogleLogin.as_view()


class UserListView(generics.ListAPIView):
    queryset = models.User.objects.all()
    serializer_class = serializers.UserSerializer
