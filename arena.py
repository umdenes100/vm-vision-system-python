import math
import processed_marker
import cv2

origin = [0,0]
axis = [4,4]
mPpm = 1
width = 4
height = 2
pixels_Meter = 1.0
theta = 3.1415
m_list = []

def process_Markers(frame, marker_list):
    print("starting process for markers")
    # process corners of arena
    for x in marker_list:
        if x.id == 0:
            origin = x.corner1
        elif x.id == 1:
            axis = x.corner1
        else:
            break
    
    pixels_Meter = math.sqrt((axis[0] - origin[0])*(axis[0] - origin[0]) + (axis[1] - origin[1]) * (axis[1] - origin[1])) / width
    theta = -math.atan2(axis[1] - origin[1], axis[0] - origin[0])
    
    print("processed corners")
    # process markers on arena for teams
    for x in marker_list:
        if x.id > 1:
            n_marker = translate(x)
            m_list.append(n_marker)
            frame = cv2.arrowedLine(frame,(int(x.corner1[0]), int(x.corner1[1])),(int(x.corner2[0]), int(x.corner2[1])),(0, 255, 0),3)
    
    print("processed other markers")
    return frame
    

def translate(marker):
    print("test")
    # mArenaMutex.lock();
    # // Calculate theta of the marker by comparing the degree of the line created
    # // by two corners with the degree of the arena

    mtheta = theta - math.atan2(marker.corner2[1] - marker.corner1[1], marker.corner2[0] - marker.corner1[0])


    # // Subtract away the origin
    fx = marker.corner1[0] - origin[0]
    fy = origin[1] - marker.corner1[1]
    # float fx = m.x[0] - mOriginPx[0];
    # float fy = mOriginPx[1] - m.y[0];

    # // Convert camera frame of reference to arena frame of reference
    A = fx * math.cos(theta) + fy * math.sin(theta)
    B = fy * math.cos(theta) - fx * math.sin(theta)

    # // Shift measurement to center of marker
    # //float markerSide = sqrt((m[1].x - m[0].x)*(m[1].x - m[0].x) + (m[1].y - m[0].y)*(m[1].y - m[0].y));
    markerSide = math.sqrt((marker.corner2[0] - marker.corner1[0])*(marker.corner2[0] - marker.corner1[0]) + 
    (marker.corner2[1] - marker.corner1[1])*(marker.corner2[1] - marker.corner1[1]))
    PI = 3.1415
    if (math.cos(mtheta) >= 0) :
         A += math.sqrt(2) * markerSide / 2 * math.cos(PI/4 - mtheta)
         B -= math.sqrt(2) * markerSide / 2 * math.sin(PI/4 - mtheta)
    else :
         A -= math.sqrt(2) * markerSide / 2 * math.sin(theta - 3*PI/4)
         B += math.sqrt(2) * markerSide / 2 * math.cos(theta - 3*PI/4)
    

    # // Convert to meters and store into Marker
    x = A / pixels_Meter
    y = B / pixels_Meter

    # mArenaMutex.unlock();

    n_marker = processed_marker.processed_Marker(marker.id, x, y, mtheta)


    return n_marker
