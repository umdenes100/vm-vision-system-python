import logging
import math
# noinspection PyUnresolvedReferences
import numpy as np
import cv2

from components.data import ProcessedMarker, dr_op


def center(corners: list[tuple]):
    """
    :param corners: list of corners of the marker
    :return: the center of the marker
    """
    x = 0
    y = 0
    for corner in corners:
        x += corner[0]
        y += corner[1]
    x /= len(corners)
    y /= len(corners)
    return int(x), int(y)


def getHomographyMatrix(marker_list):
    """
    :param marker_list: list of markers
    :return: the homography matrix or None if there are not enough markers
    """
    pt00 = None
    pt02 = None
    pt40 = None
    pt42 = None
    for aruco_id, corners in marker_list:
        if aruco_id == 0:  # finding all the corners of the arena. Corners are clockwise starting from 0 0.
            pt00 = center(corners)
        elif aruco_id == 1:
            pt02 = center(corners)
        elif aruco_id == 2:
            pt42 = center(corners)
        elif aruco_id == 3:
            pt40 = center(corners)

    if pt00 is None or pt02 is None or pt40 is None or pt42 is None:
        logging.debug("One of the markers is blocked - cannot generate homography matrix")
        return None
    src_pts = np.float32([pt00, pt40, pt02, pt42])  # pixel coordinates of the markers
    dst_pts = np.float32([[0.0, 0.0], [4.0, 0.0], [0.0, 2.0], [4.0, 2.0]])  # arena coordinates of markers
    homography_matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)  # this gives us the homography matrix of the arena
    logging.debug("Generated Homography Matrix!!!")
    return homography_matrix


def processMarkers(marker_list):
    markers: dict[int: ProcessedMarker] = {0: ProcessedMarker(0, -1.0, -1.0, (-1, -1), -1.0),
                                           1: ProcessedMarker(1, -1.0, -1.0, (-1, -1), -1.0),
                                           2: ProcessedMarker(2, -1.0, -1.0, (-1, -1), -1.0),
                                           3: ProcessedMarker(3, -1.0, -1.0, (-1, -1), -1.0)}
    try:
        for marker in marker_list:
            if marker[0] > 3:
                p_marker: ProcessedMarker = translate(marker[0], marker[1], dr_op.H)
                markers[p_marker.id] = p_marker
    except Exception as e:
        logging.debug(e)
    # returned the processed image frame and marker list
    return markers


def createMission(frame, inverse_matrix, theta, mission_loc, start_loc):
    y = [.55, 1.45]  # possible y coordinates of the mission and otv
    # inverse_matrix = np.linalg.pinv(H) #find the inverse matrix of the homography matrix
    red = (142, 80, 233)  # Note, opencv does colors in (B,G,R)
    white = (255, 255, 255)

    try:
        # draws the mission site
        point1 = np.float32(np.array([[[0.575, y[mission_loc]]]]))
        transformed_1 = cv2.perspectiveTransform(point1, inverse_matrix)
        frame = cv2.circle(frame, (int(transformed_1[0, 0, 0]), int(transformed_1[0, 0, 1])), 40, red, 2)

        # finding the coordinates of two points of arrowed line
        # the start of the arrow
        x_c = .175 * math.cos(theta) + 0.575  # using 0.575 instead of 0.55 to accound for camera angle
        y_c = .175 * math.sin(theta) + y[start_loc]
        # the tip of the arrow
        x_s = .10 * math.cos(theta - math.pi) + 0.575
        y_s = .10 * math.sin(theta - math.pi) + y[start_loc]

        # drawing the arrowed line
        point1 = np.float32(np.array([[[x_s, y_s]]]))
        point2 = np.float32(np.array([[[x_c, y_c]]]))
        transformed_1 = cv2.perspectiveTransform(point1, inverse_matrix)
        transformed_2 = cv2.perspectiveTransform(point2, inverse_matrix)
        frame = cv2.arrowedLine(frame, (int(transformed_2[0, 0, 0]), int(transformed_2[0, 0, 1])),
                                (int(transformed_1[0, 0, 0]), int(transformed_1[0, 0, 1])), white, 3)
        # drawing the otv box, x-coordinate will always be .55 as the center
        point1 = np.float32(np.array([[[0.55 - 0.20, y[start_loc] - 0.20]]]))  # bottom left corner of square
        point2 = np.float32(np.array([[[0.55 + 0.20, y[start_loc] + 0.20]]]))  # top right corner of square
        transformed_1 = cv2.perspectiveTransform(point1, inverse_matrix)
        transformed_2 = cv2.perspectiveTransform(point2, inverse_matrix)
        frame = cv2.rectangle(frame, (int(transformed_1[0, 0, 0]), int(transformed_1[0, 0, 1])),
                              (int(transformed_2[0, 0, 0]), int(transformed_2[0, 0, 1])), white, 3)
    except Exception as e:
        print("EXCEPTION (createMission): " + str(e))
        with open('errors.txt', 'a') as f:
            f.write("EXCEPTION (createMission): " + str(e))
    return frame


def createObstacles(frame, inverse_matrix, instruction):
    possible_x = [1.40, 2.23]  # possible x-coords of obstacles
    possible_y = [1.25, 0.75, 0.25]  # possible y-coords of obstacles, in decreasing order due to randomization
    rows = [0, 1, 2]  # keeps track of which rows have obstacles filled by removing that row from the list
    x_length = 0.2  # equiv to 20cm
    y_length = 0.5  # equiv to 50cm
    blue = (185, 146, 68)  # color of solid obstacle
    gold = (25, 177, 215)  # color of traversable obstacle
    # inverse_matrix = np.linalg.pinv(H) # inverts the homography matrix so we can convert arena coords to pixel coords
    try:
        # draw out the solid obstacles
        for x in range(2):
            placement = int(instruction[x])
            point1 = np.float32(np.array([[[possible_x[x], possible_y[placement]]]]))  # bottom left corner
            point2 = np.float32(
                np.array([[[possible_x[x] + x_length, possible_y[placement] + y_length]]]))  # top right corner
            point3 = np.float32(np.array([[[possible_x[x] + 0.05, possible_y[placement] + 0.25]]]))  # text poisition

            rows.remove(placement)  # removed processed markers, probably a more efficient way to do this but it works

            # transforms arena coordinates to pixel coordinates
            transformed_1 = cv2.perspectiveTransform(point1, inverse_matrix)
            transformed_2 = cv2.perspectiveTransform(point2, inverse_matrix)
            text = cv2.perspectiveTransform(point3, inverse_matrix)

            # tranformed will give a float array, got to cast to int for this to work properly
            frame = cv2.rectangle(frame, (int(transformed_1[0, 0, 0]), int(transformed_1[0, 0, 1])),
                                  (int(transformed_2[0, 0, 0]), int(transformed_2[0, 0, 1])), blue, 3)
            frame = cv2.putText(frame, 'S', (int(text[0, 0, 0]), int(text[0, 0, 1])), cv2.FONT_HERSHEY_SIMPLEX,
                                1, (255, 0, 0), 2, cv2.LINE_AA)

        # drawing out the traversable object
        placement = instruction[2]
        if placement == "A":
            point1 = np.float32(np.array([[[possible_x[0], possible_y[rows[0]]]]]))
            point2 = np.float32(np.array([[[possible_x[0] + x_length, possible_y[rows[0]] + y_length]]]))
            point3 = np.float32(np.array([[[possible_x[0] + 0.05, possible_y[rows[0]] + 0.25]]]))
        else:
            point1 = np.float32(np.array([[[possible_x[1], possible_y[rows[0]]]]]))
            point2 = np.float32(np.array([[[possible_x[1] + x_length, possible_y[rows[0]] + y_length]]]))
            point3 = np.float32(np.array([[[possible_x[1] + 0.05, possible_y[rows[0]] + 0.25]]]))

        transformed_1 = cv2.perspectiveTransform(point1, inverse_matrix)
        transformed_2 = cv2.perspectiveTransform(point2, inverse_matrix)

        text = cv2.perspectiveTransform(point3, inverse_matrix)

        # tranformed will give a float array, got to cast to int for this to work properly
        frame = cv2.rectangle(frame, (int(transformed_1[0, 0, 0]), int(transformed_1[0, 0, 1])),
                              (int(transformed_2[0, 0, 0]), int(transformed_2[0, 0, 1])), gold, 3)
        frame = cv2.putText(frame, 'T', (int(text[0, 0, 0]), int(text[0, 0, 1])), cv2.FONT_HERSHEY_SIMPLEX,
                            1, (255, 0, 0), 2, cv2.LINE_AA)
    except Exception as e:
        exception_str = "EXCEPTION (createObstacles): " + str(e) + "\n"
        print(exception_str)
        with open('errors.txt', 'a') as f:
            f.write(exception_str)
        return frame
    return frame


def translate(i, corners, H) -> ProcessedMarker:
    # find the center of the marker in pixels # don't know why you need so many brackets, but this makes it work
    marker_coords_px = np.float32(np.array([[[0.0, 0.0]]]))
    marker_coords_px[0, 0, 0] = (corners[0][0] + corners[1][0] + corners[2][0] + corners[3][0]) / 4
    marker_coords_px[0, 0, 1] = (corners[0][1] + corners[1][1] + corners[2][1] + corners[3][1]) / 4

    # marker_coords_px = center(corners)

    # Use homography transformation matrix to convert marker coords in px to meters
    marker_coords_m = cv2.perspectiveTransform(marker_coords_px, H)[0]

    # Find theta of the marker
    corner1_coords_m = cv2.perspectiveTransform(np.float32(np.array([[corners[0]]])), H)
    corner2_coords_m = cv2.perspectiveTransform(np.float32(np.array([[corners[1]]])), H)
    marker_theta = math.atan2(corner2_coords_m[0, 0, 1] - corner1_coords_m[0, 0, 1],
                              corner2_coords_m[0, 0, 0] - corner1_coords_m[0, 0, 0])
    n_marker = ProcessedMarker(i, marker_coords_m[0, 0], marker_coords_m[0, 1], center(corners), marker_theta)
    return n_marker
