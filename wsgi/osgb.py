from __future__ import division

from collections import namedtuple
import math


LAND_RANGER_LETTERS = 'ABCDEFGHJKLMNOPQRSTUVWXYZ'

LR_LETTER_TO_COORDS = {char: (i % 5, 4 - i//5)
                       for i, char in enumerate(LAND_RANGER_LETTERS)}
LR_COORDS_TO_LETTER = {(i % 5, 4 - i//5): char
                       for i, char in enumerate(LAND_RANGER_LETTERS)}

MAJOR_SIZE = 500 * 1000
MINOR_SIZE = 100 * 1000


def is_land_ranger(grid_ref):
    return (len(grid_ref) in (8, 10) and grid_ref[:2].isalpha() and
            grid_ref[0] in LAND_RANGER_LETTERS and
            grid_ref[1] in LAND_RANGER_LETTERS and
            grid_ref[2:].isdigit())


def is_osgb(grid_ref):
    return (len(grid_ref.split(',')) == 2 and
            all(part.strip().isdigit() for part in grid_ref.split(',')))


def land_ranger_to_osgb(grid_ref):
    major, minor = grid_ref[:2]
    if len(grid_ref) == 8:
        x, y = grid_ref[2:5], grid_ref[5:]
        scale = 100
    else:
        x, y = grid_ref[2:6], grid_ref[6:]
        scale = 10
    # TODO: major
    easting = 100 * 1000 * LR_LETTER_TO_COORDS[minor][0] + int(x) * scale
    northing = 100 * 1000 * LR_LETTER_TO_COORDS[minor][1] + int(y) * scale
    return easting, northing


def osgb_to_land_ranger(easting, northing):
    # Let's be lazy and check we're in the major S square.
    assert 0 <= easting < 500 * 1000
    assert 0 <= northing < 500 * 1000
    grid_ref = 'S'
    coords = (easting // MINOR_SIZE, northing // MINOR_SIZE)
    grid_ref += LR_COORDS_TO_LETTER[coords]
    three_digit = lambda value: (value % MINOR_SIZE) // 100
    grid_ref += '{:03}{:03}'.format(three_digit(easting), three_digit(northing))
    return grid_ref


############################################################################
#
# Subsequent code ported from: http://smdcs.org.uk/gis/js/cords_convert.js
#

def osgb_to_wgs84_lat_long(E, N):
    # Airy 1830 major & minor semi-axes
    a = 6377563.396
    b = 6356256.910
    # NatGrid scale factor on central meridian
    F0 = 0.9996012717
    # NatGrid true origin
    lat0 = 49*math.pi/180
    lon0 = -2*math.pi/180
    # northing & easting of true origin, metres
    N0 = -100000
    E0 = 400000
    # eccentricity squared
    e2 = 1 - (b*b)/(a*a)

    n = (a-b)/(a+b)
    n2 = n*n
    n3 = n*n*n;

    lat=lat0
    M=0

    while (N-N0-M >= 0.00001):  # ie until < 0.01mm
        lat = (N-N0-M)/(a*F0) + lat

        Ma = (1 + n + (5/4)*n2 + (5/4)*n3) * (lat-lat0)
        Mb = (3*n + 3*n*n + (21/8)*n3) * math.sin(lat-lat0) * math.cos(lat+lat0)
        Mc = ((15/8)*n2 + (15/8)*n3) * math.sin(2*(lat-lat0)) * math.cos(2*(lat+lat0))
        Md = (35/24)*n3 * math.sin(3*(lat-lat0)) * math.cos(3*(lat+lat0));
        M = b * F0 * (Ma - Mb + Mc - Md)  # meridional arc

    cosLat = math.cos(lat)
    sinLat = math.sin(lat)
    nu = a*F0/math.sqrt(1-e2*sinLat*sinLat)  # transverse radius of curvature
    rho = a*F0*(1-e2)/math.pow(1-e2*sinLat*sinLat, 1.5)  # meridional radius of curvature
    eta2 = nu/rho-1;

    tanLat = math.tan(lat)
    tan2lat = tanLat*tanLat
    tan4lat = tan2lat*tan2lat
    tan6lat = tan4lat*tan2lat
    secLat = 1/cosLat;
    nu3 = nu*nu*nu
    nu5 = nu3*nu*nu
    nu7 = nu5*nu*nu
    VII = tanLat/(2*rho*nu)
    VIII = tanLat/(24*rho*nu3)*(5+3*tan2lat+eta2-9*tan2lat*eta2)
    IX = tanLat/(720*rho*nu5)*(61+90*tan2lat+45*tan4lat)
    X = secLat/nu
    XI = secLat/(6*nu3)*(nu/rho+2*tan2lat)
    XII = secLat/(120*nu5)*(5+28*tan2lat+24*tan4lat)
    XIIA = secLat/(5040*nu7)*(61+662*tan2lat+1320*tan4lat+720*tan6lat)

    dE = (E-E0)
    dE2 = dE*dE
    dE3 = dE2*dE
    dE4 = dE2*dE2
    dE5 = dE3*dE2
    dE6 = dE4*dE2
    dE7 = dE5*dE2
    lat = lat - VII*dE2 + VIII*dE4 - IX*dE6
    lon = lon0 + X*dE - XI*dE3 + XII*dE5 - XIIA*dE7

    lat, lon = math.degrees(lat), math.degrees(lon)
    lat, lon = convertOSGB36toWGS84(LatLon(lat, lon))
    return lat, lon


class LatLon(object):
    def __init__(self, lat, lon, height=0):
        self.lat = lat
        self.lon = lon
        self.height = height


Ellipse = namedtuple('Ellipse', ['a', 'b', 'f'])


# ellipse parameters
e = {'WGS84': Ellipse(a=6378137, b=6356752.3142, f=1/298.257223563),
     'Airy1830': Ellipse(a=6377563.396, b=6356256.910, f=1/299.3249646)}


Helmert = namedtuple('Helmert', ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 's'])


# helmert transform parameters
h = {'WGS84toOSGB36': Helmert(tx=-446.448, ty=125.157, tz=-542.060,  # m
                              rx=-0.1502, ry=-0.2470, rz=-0.8421,  # sec
                              s=20.4894),  # ppm
     'OSGB36toWGS84': Helmert(tx=446.448, ty=-125.157, tz=542.060,
                              rx=0.1502, ry=0.2470, rz=0.8421,
                              s=-20.4894)}


def convertOSGB36toWGS84(p1):
    return convert(p1, e['Airy1830'], h['OSGB36toWGS84'], e['WGS84'])


def convertWGS84toOSGB36(p1):
    return convert(p1, e['WGS84'], h['WGS84toOSGB36'], e['Airy1830'])


def convert(p, e1, t, e2):
    # Convert polar to cartesian coordinates (using ellipse 1)
    p1 = LatLon(math.radians(p.lat), math.radians(p.lon), p.height)  # to avoid modifying passed param

    a = e1.a
    b = e1.b

    sinPhi = math.sin(p1.lat)
    cosPhi = math.cos(p1.lat)
    sinLambda = math.sin(p1.lon)
    cosLambda = math.cos(p1.lon)
    H = p1.height

    eSq = (a*a - b*b) / (a*a)
    nu = a / math.sqrt(1 - eSq*sinPhi*sinPhi)

    x1 = (nu+H) * cosPhi * cosLambda
    y1 = (nu+H) * cosPhi * sinLambda
    z1 = ((1-eSq)*nu + H) * sinPhi


    # apply helmert transform using appropriate params

    tx = t.tx
    ty = t.ty
    tz = t.tz
    rx = t.rx/3600 * math.pi/180  # normalise seconds to radians
    ry = t.ry/3600 * math.pi/180
    rz = t.rz/3600 * math.pi/180
    s1 = t.s/1e6 + 1  # normalise ppm to (s+1)

    # apply transform
    x2 = tx + x1*s1 - y1*rz + z1*ry
    y2 = ty + x1*rz + y1*s1 - z1*rx
    z2 = tz - x1*ry + y1*rx + z1*s1


    # convert cartesian to polar coordinates (using ellipse 2)

    a = e2.a
    b = e2.b
    precision = 4 / a  # results accurate to around 4 metres

    eSq = (a*a - b*b) / (a*a)
    p = math.sqrt(x2*x2 + y2*y2)
    phi = math.atan2(z2, p*(1-eSq))
    phiP = 2*math.pi
    while abs(phi-phiP) > precision:
        nu = a / math.sqrt(1 - eSq*math.sin(phi)*math.sin(phi))
        phiP = phi
        phi = math.atan2(z2 + eSq*nu*math.sin(phi), p)
    lambda_rad = math.atan2(y2, x2)
    #H = p/math.cos(phi) - nu

    return math.degrees(phi), math.degrees(lambda_rad)
