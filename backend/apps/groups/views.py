from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsFarmer

from . import services
from .models import FarmerGroup, GroupMembership, MembershipRole, MembershipStatus

FARMER_ONLY = [IsAuthenticated, IsFarmer]


class GroupSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, default=0)
    my_status = serializers.CharField(read_only=True, default=None)
    distance = serializers.DictField(read_only=True, default=None)

    class Meta:
        model = FarmerGroup
        fields = ["id", "name", "description", "group_type", "focus", "province", "municipality", "town", "is_open",
                  "member_count", "my_status", "distance", "created_at"]
        read_only_fields = ["id", "created_at"]


class MemberSerializer(serializers.ModelSerializer):
    farmer_id = serializers.IntegerField(read_only=True)
    display_name = serializers.CharField(source="farmer.display_name", read_only=True)

    class Meta:
        model = GroupMembership
        fields = ["farmer_id", "display_name", "role", "status", "created_at"]


class PostSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    author_display_name = serializers.CharField(source="author.display_name", read_only=True)
    body = serializers.CharField(max_length=4000)
    is_announcement = serializers.BooleanField(default=False)
    created_at = serializers.DateTimeField(read_only=True)


FarmerIdSerializer = inline_serializer("FarmerId", {"farmer_id": serializers.IntegerField()})
RoleSerializer = inline_serializer("MemberRole", {"farmer_id": serializers.IntegerField(),
                                                  "role": serializers.ChoiceField(MembershipRole.values)})
DecisionSerializer = inline_serializer("JoinDecision", {"farmer_id": serializers.IntegerField(required=False),
                                                        "accept": serializers.BooleanField()})


def _int(request, name):
    try:
        return int(request.data.get(name))
    except (TypeError, ValueError):
        raise serializers.ValidationError({name: ["Required."]})


def _bool(request, name):
    value = request.data.get(name)
    if not isinstance(value, bool):
        raise serializers.ValidationError({name: ["Must be true or false."]})
    return value


class GroupListView(ListAPIView):
    """Search groups (nearest first) or ``?mine=true`` for yours. POST creates a group with you as admin."""

    permission_classes = FARMER_ONLY
    serializer_class = GroupSerializer

    @extend_schema(parameters=[OpenApiParameter(n, str) for n in ("q", "group_type", "province", "municipality",
                                                                  "town", "focus")]
                   + [OpenApiParameter("max_distance_km", int), OpenApiParameter("mine", bool)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        p = self.request.query_params
        max_km = p.get("max_distance_km")
        return services.search_groups(
            self.request.user, q=p.get("q"), group_type=p.get("group_type"), province=p.get("province"),
            municipality=p.get("municipality"), town=p.get("town"), focus=p.get("focus"),
            max_distance_km=int(max_km) if max_km and max_km.isdigit() else None,
            mine=p.get("mine") in ("true", "1"))

    @extend_schema(request=GroupSerializer, responses={201: GroupSerializer})
    def post(self, request):
        s = GroupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        group = services.create_group(request.user, **s.validated_data)
        return Response(GroupSerializer(group).data, status=status.HTTP_201_CREATED)


class GroupDetailView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(responses=inline_serializer("GroupDetail", {"group": GroupSerializer(),
                                                               "members": MemberSerializer(many=True)}))
    def get(self, request, pk):
        group = services.get_group(pk)
        m = services.membership(group, request.user)
        is_admin = bool(m and m.status == MembershipStatus.ACTIVE and m.role == MembershipRole.ADMIN)
        members = group.memberships.select_related("farmer").filter(
            status__in=[MembershipStatus.ACTIVE] + ([MembershipStatus.REQUESTED, MembershipStatus.INVITED]
                                                    if is_admin else []))
        group.my_status = m.status if m else None
        group.member_count = group.memberships.filter(status=MembershipStatus.ACTIVE).count()
        return Response({"group": GroupSerializer(group).data, "members": MemberSerializer(members, many=True).data})


class _GroupAction(APIView):
    permission_classes = FARMER_ONLY

    def done(self, m):
        return Response(MemberSerializer(m).data)


class JoinView(_GroupAction):
    """Open group: you join at once. Closed group: your request waits for an admin. Accepts invitations too."""

    @extend_schema(request=None, responses=MemberSerializer)
    def post(self, request, pk):
        return self.done(services.join(request.user, pk))


class LeaveView(_GroupAction):
    @extend_schema(request=None, responses=MemberSerializer)
    def post(self, request, pk):
        return self.done(services.leave(request.user, pk))


class InviteView(_GroupAction):
    @extend_schema(request=FarmerIdSerializer, responses=MemberSerializer)
    def post(self, request, pk):
        return self.done(services.invite(request.user, pk, _int(request, "farmer_id")))


class RespondInviteView(_GroupAction):
    @extend_schema(request=DecisionSerializer, responses=MemberSerializer)
    def post(self, request, pk):
        return self.done(services.respond_to_invite(request.user, pk, _bool(request, "accept")))


class DecideRequestView(_GroupAction):
    """Admin approves (accept=true) or declines a join request."""

    @extend_schema(request=DecisionSerializer, responses=MemberSerializer)
    def post(self, request, pk):
        return self.done(services.decide_request(request.user, pk, _int(request, "farmer_id"),
                                                 _bool(request, "accept")))


class RemoveMemberView(_GroupAction):
    @extend_schema(request=FarmerIdSerializer, responses=MemberSerializer)
    def post(self, request, pk):
        return self.done(services.remove_member(request.user, pk, _int(request, "farmer_id")))


class SetRoleView(_GroupAction):
    """Admin promotes a member to ADMIN (or demotes to MEMBER while another admin remains)."""

    @extend_schema(request=RoleSerializer, responses=MemberSerializer)
    def post(self, request, pk):
        role = request.data.get("role")
        if role not in MembershipRole.values:
            raise serializers.ValidationError({"role": ["Use ADMIN or MEMBER."]})
        return self.done(services.set_role(request.user, pk, _int(request, "farmer_id"), role))


class PostListView(APIView):
    """Group posts (members only). Only admins can post announcements."""

    permission_classes = FARMER_ONLY

    @extend_schema(responses=PostSerializer(many=True))
    def get(self, request, pk):
        from apps.core.pagination import StandardPagination

        paginator = StandardPagination()
        page = paginator.paginate_queryset(services.list_posts(request.user, pk), request, view=self)
        return paginator.get_paginated_response(PostSerializer(page, many=True).data)

    @extend_schema(request=PostSerializer, responses={201: PostSerializer})
    def post(self, request, pk):
        s = PostSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        post = services.create_post(request.user, pk, s.validated_data["body"], s.validated_data["is_announcement"])
        return Response(PostSerializer(post).data, status=status.HTTP_201_CREATED)
