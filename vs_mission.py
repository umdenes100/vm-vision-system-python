# return the proper mission message based on mission type and curr index of mission value
import logging


def get_mission_message(mission: str, mission_message_type: int, msg: str):
    try:
        msg = int(msg)
    except ValueError:
        logging.debug(f'Invalid mission message: {msg}')
        return None

    mission_string: str = ''
    if mission == "CRASH_SITE":  # Crash Site
        if mission_message_type == 0:  # DIRECTION
            mission_string += "The direction of the abnormality is in the "
            if msg == 0:
                mission_string += "+x"
            elif msg == 1:
                mission_string += "-x"
            elif msg == 2:
                mission_string += "+y"
            elif msg == 3:
                mission_string += "-y"
            else:
                mission_string += "?????"
            mission_string += " direction."
        elif mission_message_type == 1:  # LENGTH
            mission_string += f"The length of the side with abnormality is {msg}mm."
        elif mission_message_type == 2:  # HEIGHT
            mission_string += f"The height of the side with abnormality is {msg}mm."
        else:
            mission_string += "Not a valid mission type!"

    elif mission == "DATA":  # Data
        if mission_message_type == 0:  # DUTY CYCLE
            mission_string += f'The duty cycle is {msg}%.'
        elif mission_message_type == 1:  # MAGNETISM
            mission_string += "The disk is "
            if msg == 0:
                mission_string += "MAGNETIC"
            elif msg == 1:
                mission_string += "NOT MAGNETIC"
            else:
                mission_string += "?????"
            mission_string += "."
        else:
            mission_string += "Not a valid mission type!"

    elif mission == "MATERIAL":  # Material
        if mission_message_type == 0:  # WEIGHT
            mission_string += "The weight of the material is "
            if msg == 0:
                mission_string += "HEAVY"
            elif msg == 1:
                mission_string += "MEDIUM"
            elif msg == 2:
                mission_string += "LIGHT"
            else:
                mission_string += "?????"
            mission_string += "."
        elif mission_message_type == 1:  # SQUISHABILITY
            mission_string += "The material is "
            if msg == 0:
                mission_string += "SQUISHY"
            elif msg == 1:
                mission_string += "NOT SQUISHY"
            else:
                mission_string += "?????"
            mission_string += "."
        else:
            mission_string += "Not a valid mission type!"

    elif mission == "FIRE":  # Fire
        if mission_message_type == 0:  # NUM_CANDLES
            mission_string += f"The number of candles alit is {msg}."
        elif mission_message_type == 1:  # TOPOGRAPHY
            mission_string += "The topography of the fire mission is: "
            if msg == 0:
                mission_string += "A"
            elif msg == 1:
                mission_string += "B"
            elif msg == 2:
                mission_string += "C"
            else:
                mission_string += "?????"
        else:
            mission_string += "Not a valid mission type!"

    elif mission == "WATER":  # Water
        if mission_message_type == 0:  # DEPTH
            mission_string += f"The depth of the water is {msg}mm."
        elif mission_message_type == 1:  # WATER_TYPE
            mission_string += "The water is "
            if msg == 0:
                mission_string += "FRESH and UNPOLLUTED."
            elif msg == 1:
                mission_string += "FRESH and POLLUTED"
            elif msg == 2:
                mission_string += "SALTY and UNPOLLUTED"
            elif msg == 3:
                mission_string += "SALTY and POLLUTED"
            else:
                mission_string += "?????"
        else:
            mission_string += "Not a valid mission type!"

    else:
        mission_string = f"ERROR - invalid mission type ({mission})"

    return 'MISSION MESSAGE: ' + mission_string + '\n'
