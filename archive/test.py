# Python code to read image
import cv2
import numpy as np 
import aruco_marker
# To read image from disk, we use
# cv2.imread function, in below method,
frame= cv2.imread("photos/arena_marker.jpg", cv2.IMREAD_COLOR)

arucoDict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_1000)
arucoParams = cv2.aruco.DetectorParameters_create()
(corners, ids, rejected) = cv2.aruco.detectMarkers(frame, arucoDict, parameters=arucoParams)
frame = cv2.aruco.drawDetectedMarkers(frame,corners,ids)

marker_list = []
for x in range(len(ids)):
    curr_Marker = aruco_marker.Marker(ids[x],corners[x][0][0],corners[x][0][1],corners[x][0][2],corners[x][0][3])
    marker_list.append(curr_Marker)

# # Display the resulting frame
cv2.imshow('frame',frame)
cv2.waitKey(0)
cv2.destroyAllWindows()
