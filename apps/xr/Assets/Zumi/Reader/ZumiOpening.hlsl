// The window a place is seen through, shared by Zumi/Place (what of the place shows) and Zumi/Breach (the broken wall
// or the rift around it). The window follows the wall: a rounded rectangle on the wall's surface laid flat, metres
// along the walls (the key wall, then on round a corner along a side wall it folds onto) by world height, so its edges
// run parallel to the wall's sides, the sill and the ceiling, and a fold onto a side wall has no seam. A point of a
// wall is found where the line of sight leaves the room through the window's planes.
// Include it after the CBUFFER that declares these:
//   _Key      a point of the key wall           _KeyN  its normal into the room     _KeyR  right along it
//   _SideL/_SideR   a point of a side wall (w: 1 when the window folds onto it)      _SideLN/_SideRN  their normals
//   _Rect     the window: from, to along the walls (metres from _Key along _KeyR, laid flat), bottom, top (world y)
//   _Round    its corners' radius, the width of its soft edge, both in metres
#ifndef ZUMI_OPENING_INCLUDED
#define ZUMI_OPENING_INCLUDED

float ZumiHash(float n) { return frac(sin(n * 91.3458) * 47453.5453); }

// noise along a line, piecewise linear: straight runs between random corners, as a broken edge runs
float ZumiJag1(float x, float seed)
{
    float i = floor(x);
    return lerp(ZumiHash(i + seed), ZumiHash(i + 1.0 + seed), x - i);
}

// the same around the outline, u in [0, 1), wrapping over cells
float ZumiJag(float u, float cells, float seed)
{
    float x = u * cells;
    float i = floor(x);
    return lerp(ZumiHash(fmod(i, cells) + seed), ZumiHash(fmod(i + 1.0, cells) + seed), x - i);
}

// how far the broken wall's edge is notched in at u around the outline, in metres: up to 0.12
float ZumiNotch(float u)
{
    return 0.065 * ZumiJag(u, 23.0, 3.0) + 0.035 * ZumiJag(u, 57.0, 11.0) + 0.02 * ZumiJag(u, 131.0, 23.0);
}

void ZumiPlane(float3 p, float3 n, float3 eye, float3 ray, float depth, inout float t)
{
    float toward = dot(ray, n);
    if (toward < -1e-5)
    {
        float hit = dot(p - n * depth - eye, n) / toward;
        if (hit > 0.0) t = min(t, hit);
    }
}

// where the line of sight from eye along ray leaves the room through the window's planes, each pushed depth metres
// into its wall
float3 ZumiExit(float3 eye, float3 ray, float depth)
{
    float t = 1e9;
    ZumiPlane(_Key.xyz, _KeyN.xyz, eye, ray, depth, t);
    if (_SideL.w > 0.5) ZumiPlane(_SideL.xyz, _SideLN.xyz, eye, ray, depth, t);
    if (_SideR.w > 0.5) ZumiPlane(_SideR.xyz, _SideRN.xyz, eye, ray, depth, t);
    return eye + ray * t;
}

// metres a wall point lies in front of the key wall: 0 on it, how far along a side wall from the corner
float ZumiPast(float3 w) { return max(0.0, dot(w - _Key.xyz, _KeyN.xyz)); }

// a wall point on the walls laid flat: metres along them from _Key, world height
float2 ZumiFlat(float3 w)
{
    float along = dot(w - _Key.xyz, _KeyR.xyz);
    float past = ZumiPast(w);
    return float2(along + (along < (_Rect.x + _Rect.y) * 0.5 ? -past : past), w.y);
}

// signed metres from the window's rounded outline (< 0 inside), and u in [0, 1) around it
float ZumiOutline(float2 p, out float u)
{
    float2 c = float2(_Rect.x + _Rect.y, _Rect.z + _Rect.w) * 0.5;
    float2 h = float2(_Rect.y - _Rect.x, _Rect.w - _Rect.z) * 0.5;
    float r = min(_Round.x, min(h.x, h.y));
    float2 q = abs(p - c) - (h - r);
    u = atan2((p.y - c.y) / h.y, (p.x - c.x) / h.x) / 6.2831853 + 0.5;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

// the same with the broken wall's notches, the whole figure grown from the middle by open
float ZumiBroken(float2 p, float open)
{
    float2 c = float2(_Rect.x + _Rect.y, _Rect.z + _Rect.w) * 0.5;
    float u;
    float d = ZumiOutline(c + (p - c) / max(open, 1e-3), u);
    return d + ZumiNotch(u);
}

#endif
