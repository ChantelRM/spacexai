from django.urls import path

from . import views

app_name = "groups"

urlpatterns = [
    path("", views.GroupListView.as_view(), name="list"),
    path("<int:pk>/", views.GroupDetailView.as_view(), name="detail"),
    path("<int:pk>/join/", views.JoinView.as_view(), name="join"),
    path("<int:pk>/leave/", views.LeaveView.as_view(), name="leave"),
    path("<int:pk>/invite/", views.InviteView.as_view(), name="invite"),
    path("<int:pk>/invitation/", views.RespondInviteView.as_view(), name="respond-invite"),
    path("<int:pk>/requests/decide/", views.DecideRequestView.as_view(), name="decide-request"),
    path("<int:pk>/members/remove/", views.RemoveMemberView.as_view(), name="remove-member"),
    path("<int:pk>/members/role/", views.SetRoleView.as_view(), name="set-role"),
    path("<int:pk>/posts/", views.PostListView.as_view(), name="posts"),
]
