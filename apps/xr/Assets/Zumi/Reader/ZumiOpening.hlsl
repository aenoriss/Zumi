// The window a place is seen through, shared by Zumi/Place (what of the place shows), Zumi/Breach (the cracks or the
// rift around it) and Zumi/Reveal (the wall's thickness inside it). The window follows the wall: a rounded rectangle
// on the wall's surface laid flat, metres along the walls (the key wall, then on round a corner along a side wall it
// folds onto) by world height, so its edges run parallel to the wall's sides, the sill and the ceiling, and a fold onto
// a side wall bends exactly on the corner line. A point of a wall is found where the line of sight leaves the room
// through the window's planes, which are the scanned walls' own planes.
// Include it after the CBUFFER that declares these:
//   _Key      a point of the key wall           _KeyN  its normal into the room     _KeyR  right along it
//   _SideL/_SideR   a point of a side wall (w: 1 when the window folds onto it)      _SideLN/_SideRN  their normals
//   _CornerL/_CornerR  a point of the corner line it shares with the key wall (w: metres along the walls there)
//   _SideLA/_SideRA    the way along the side wall from the corner into the room
//   _Rect     the window: from, to along the walls (metres from _Key along _KeyR, laid flat), bottom, top (world y)
//   _Round    its corners' radius, the width of its soft edge, both in metres
//   _Edge     -, the reveal's depth into the wall, the side walls' share of the break, metres past a corner it eases in
#ifndef ZUMI_OPENING_INCLUDED
#define ZUMI_OPENING_INCLUDED

// the reveal's plaster at the wall's face and at its far end (Zumi/Reveal), as shown (sRGB), and how many metres
// inside that far end's edge the place darkens into it (Zumi/Place)
#define ZUMI_REVEAL_FRONT float3(0.50, 0.47, 0.43)
#define ZUMI_REVEAL_BACK float3(0.13, 0.12, 0.11)
#define ZUMI_REVEAL_BLEND 0.12

// a colour as shown, in the space the shader writes
float3 ZumiLinear(float3 c)
{
#if defined(UNITY_COLORSPACE_GAMMA)
    return c;
#else
    return pow(max(c, 0.0), 2.2);
#endif
}

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

// metres a wall point lies in front of the key wall: 0 on it, past a corner as far as it is along the side wall
float ZumiPast(float3 w)
{
    // a millimetre of slack: a point the line of sight leaves through the key wall is on it, rounding aside
    float past = dot(w - _Key.xyz, _KeyN.xyz);
    if (past <= 1e-3) return 0.0;
    bool left = dot(w - _Key.xyz, _KeyR.xyz) < (_Rect.x + _Rect.y) * 0.5;
    float3 a = left ? _SideLA.xyz : _SideRA.xyz;
    return past / max(dot(a, _KeyN.xyz), 1e-3);
}

// a wall point on the walls laid flat: metres along them from _Key, world height. On the key wall along it; past a
// corner the corner's place plus how far along the side wall
float2 ZumiFlat(float3 w)
{
    float along = dot(w - _Key.xyz, _KeyR.xyz);
    float past = ZumiPast(w);
    if (past > 0.0)
    {
        bool left = along < (_Rect.x + _Rect.y) * 0.5;
        if (left && _SideL.w > 0.5) along = _CornerL.w - past;
        else if (!left && _SideR.w > 0.5) along = _CornerR.w + past;
    }
    return float2(along, w.y);
}

// the other way: the point of the walls at a place on them laid flat, exactly on its wall's plane, and that wall's
// normal
float3 ZumiWall(float2 p, out float3 n)
{
    float3 w, o;
    if (_SideL.w > 0.5 && p.x < _CornerL.w)
    {
        w = _CornerL.xyz + _SideLA.xyz * (_CornerL.w - p.x);
        n = _SideLN.xyz;
        o = _SideL.xyz;
    }
    else if (_SideR.w > 0.5 && p.x > _CornerR.w)
    {
        w = _CornerR.xyz + _SideRA.xyz * (p.x - _CornerR.w);
        n = _SideRN.xyz;
        o = _SideR.xyz;
    }
    else
    {
        w = _Key.xyz + _KeyR.xyz * p.x;
        n = _KeyN.xyz;
        o = _Key.xyz;
    }
    w.y = p.y;
    return w - n * dot(w - o, n);
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

// how much of the break a point of the walls laid flat keeps: all on the key wall, past a corner eased within _Edge.w
// to _Edge.z
float ZumiKeyShare(float2 p)
{
    float past = 0.0;
    if (_SideL.w > 0.5) past = max(past, _CornerL.w - p.x);
    if (_SideR.w > 0.5) past = max(past, p.x - _CornerR.w);
    return lerp(_Edge.z, 1.0, 1.0 - smoothstep(0.0, max(_Edge.w, 1e-4), past));
}

// metres over the sill within which the notches ease in: the sill stays straight, a flat ledge things can rest on
#define ZUMI_SILL_EASE 0.3

// the outline with the broken wall's notches (as much of them as `notched`), the whole figure grown from the middle
// by open; none along the sill
float ZumiBroken(float2 p, float open, float notched)
{
    float2 c = float2(_Rect.x + _Rect.y, _Rect.z + _Rect.w) * 0.5;
    float u;
    float2 q = c + (p - c) / max(open, 1e-3);
    float d = ZumiOutline(q, u);
    return d + ZumiNotch(u) * notched * ZumiKeyShare(p) * saturate((q.y - _Rect.z) / ZUMI_SILL_EASE);
}

// the point of the outline (notched by `notched`, grown by open) at u around it, on the walls laid flat: u is the
// angle the outline is parametrised by, so it holds along the ray from the middle and the edge is found on it
float2 ZumiEdgeAt(float u, float open, float notched)
{
    float2 c = float2(_Rect.x + _Rect.y, _Rect.z + _Rect.w) * 0.5;
    float2 h = float2(_Rect.y - _Rect.x, _Rect.w - _Rect.z) * 0.5;
    float a = (u - 0.5) * 6.2831853;
    float2 dir = float2(cos(a) * h.x, sin(a) * h.y);
    float lo = 0.0, hi = 1.5;
    [unroll] for (int i = 0; i < 18; i++)
    {
        float mid = (lo + hi) * 0.5;
        if (ZumiBroken(c + dir * mid, open, notched) < 0.0) lo = mid;
        else hi = mid;
    }
    return c + dir * lo;
}

#endif
