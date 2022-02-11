import math
import processed_marker
import numpy as np
import cv2

width = 4.0
height = 2.0
#m_list = []
def getHomographyMatrix(frame,marker_list):
    #print("doing homogrphy")
    pt00 = (50,430)
    pt02 = (50,50)
    pt40 = (590,430)
    pt42 = (590, 50)
    for x in marker_list:
        #print(f'id {x.id} = {x.corner1}')
        if x.id == 0:  #finding all the corners of the arena
            pt00 = x.corner1
        elif x.id == 1:
            pt40 = x.corner1
        elif x.id == 2:
            pt02 = x.corner1
        elif x.id == 3:
            pt42 = x.corner1
    
    #print('\n')
    src_pts = np.float32([pt00, pt40, pt02, pt42]) #pixel coordinates of the markers
    
    dst_pts = np.float32([[0.0, 0.0], [width, 0.0], [0.0, height], [width, height]]) #arena coordinates of markers
    H = cv2.getPerspectiveTransform(src_pts, dst_pts)
    #print(H.shape)
    #print("homography done")
    return H


def processMarkers(frame, marker_list, H):
    #print("processing markers")
    markers = {}
    for x in marker_list:
        if x.id > 3:
            n_marker = translate(x, H)
            markers[f'{n_marker.id}'] = n_marker
            #print(x.id)
            #m_list.append(n_marker)
            
            #Add a green arrowed line
            frame = cv2.arrowedLine(frame,(int(x.corner1[0]), int(x.corner1[1])),(int(x.corner2[0]), 
                                    int(x.corner2[1])), (0, 255, 0), 2, tipLength= .4)
    #print("processing done")
    return frame, markers
    

def translate(marker, H):
    #print("translating")
    # find the center of the marker in pixels
    marker_coords_px = np.float32(np.array([[[0.0, 0.0]]]))  # dont know why you need so many brakets, but this makes it work
    marker_coords_px[0, 0, 0] = (marker.corner1[0] + marker.corner2[0] + marker.corner3[0] + marker.corner4[0]) / 4
    marker_coords_px[0, 0, 1] = (marker.corner1[1] + marker.corner2[1] + marker.corner3[1] + marker.corner4[1]) / 4

    # Use homography transformation matrix to convert marker coords in px to meters
    marker_coords_m = cv2.perspectiveTransform(marker_coords_px, H)[0]
    #print(marker_coords_m)

    # Find theta of the marker
    corner1_coords_m = cv2.perspectiveTransform(np.float32(np.array([[marker.corner1]])), H)
    corner2_coords_m = cv2.perspectiveTransform(np.float32(np.array([[marker.corner2]])), H)
    marker_theta = math.atan2(corner2_coords_m[0, 0, 1] - corner1_coords_m[0, 0, 1], corner2_coords_m[0, 0, 0] - corner1_coords_m[0, 0, 0])
    #print(marker_theta)
    n_marker = processed_marker.processed_Marker(marker.id, marker_coords_m[0,0], marker_coords_m[0,1], marker_theta)

    #print("translation done")
    return n_marker
