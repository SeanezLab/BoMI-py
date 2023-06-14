import asyncio
import qtm
import xml.etree.ElementTree as ET
from enum import Enum
import timeit
import threading

# This script is to be used in conjunction with the Analog_Testing Project in QTM.
# First open QTM. When prompted for the filename, choose Analog_Testing.


class Channel(str, Enum):
    TORQUE = "Torque"
    VELOCITY = "Velocity"
    POSITION = "Position"

    def __str__(self):
        return self.value


class ConversionFactors():
    """
    Based on Biodex scaling factors, see SeanezLab/Research_Material/User Manuals/Biodex/A3. Analog Settings for Biodex System 4.pdf
    Ensure Application Settings --> Analog System Settings: Velocity Scaling = 0-32 deg/sec, Torque Scaling = 0-32 ft*lb (43.5 N*m), Position Scaling = Fullscale 0 - 360 deg
        Torque Conversion: V*(1 ftlb/0.1563V)*(1.3558179483 Nm/ftlb)
        Velocity Conversion: V*(1 deg/sec / 0.1563V)
        Position Conversion: V*(1 deg/0.0292V)
    **If you change the scaling factors on the Biodex, you need to change the conversion factors here
    """
    def __init__(self):
        self.torque_conv = (1/0.1563) * (1.3558179483)
        self.velocity_conv = (1/0.1563)
        self.position_conv = (1/0.0292)


def real_time_stream(q_analog, done: threading.Event, IPaddress: str, port: int, version: str):
    """
    Defines main asynchronous function, runs main coroutine
    """
    def on_packet(packet):
        """
        Pulls data from QTM, creates dictionary of packets {Torque:, Velocity, Position, Time}
        Converts QTM analog signal to correct units before adding to dictionary
        """
        info, data = packet.get_analog() #get analog data from qtm, from qtm sdk commands
        if len(data) > 0:
            data_all_elements = {}
            for i, channel in enumerate(Channel):
                data_all_elements[channel] = recv_conv(data[i][2][0][0], channel)
            data_all_elements['Time'] = timeit.default_timer()
            data_all_elements['Name'] = 'QTM'
            q_analog.put(data_all_elements)
        else:
            print("Empty data from packet")

    async def get_frames_from_qtm():
        """
        Defines main coroutine for streaming analog 'frames' from QTM
        """
        # Connect to the QTM Application. The application should be open.
        connection = await qtm.connect(IPaddress, port, version)

        if connection is None:
            print("failed to connect")
            return

        async with qtm.TakeControl(connection, 'jd'):
            await connection.new()

        param = await connection.get_parameters(parameters=["analog"])
        xml = ET.fromstring(param)
        print(xml[0][0][2].text) #Gets number of analog channels
        #print(xml[0][0][5][0].text) #Gets name of channels
        
        #Gets name of channels
        for x in xml[0][0].findall('Channel'):
            print(x[0].text) 

        print('Preparing to run in analog_streaming_client')
        while not done.is_set():
            await connection.stream_frames(components=['analog'], on_packet = on_packet)

        print('stopping in analog_streaming_client')
        await connection.stream_frames_stop()

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Set the policy to prevent "Event loop is closed" error on Windows - https://github.com/encode/httpx/issues/914
        #An event loop policy is a global object used to get and set the current event loop, as well as create new event loops. 
        #set_event_loop_policy: Set the current process-wide policy to policy. If policy is set to None, the default policy is restored.
    print('waiting to run in analog_streaming_client')
    asyncio.run(get_frames_from_qtm()) #running Coroutine

def recv_conv(data, channel: Channel):
    """
    Convert incoming data from QTM analog streaming, to units (Nm, deg/sec, deg)
    """
    factors = ConversionFactors()
    match channel:
        case Channel.TORQUE:
            return data * factors.torque_conv
        case Channel.VELOCITY:
            return data * factors.velocity_conv
        case Channel.POSITION:
            return data * factors.position_conv
        case _:
            raise ValueError("Not a valid QTM channel")


def get_channel_number(IPaddress: str, port: int, version: str):
    """
    Main asynchronus function to run main coroutine
    Connects to QTM, pulls parameters, and returns connected channels
    Currently set to use Channel 3,4,5
    """
    async def get_channels_from_qtm():
        """
        Main coroutine to connect to QTM and get channel infomation
        """
        connection = await qtm.connect(IPaddress, port, version)

        if connection is None:
            print("failed to connect")
            return

        async with qtm.TakeControl(connection, 'jd'):
            await connection.new()

        param = await connection.get_parameters(parameters=["analog"])

        xml = ET.fromstring(param)
        #print(xml[0][0][2].text) #Gets number of analog channels
        #print(xml[0][0][5][0].text) #Gets name of channels
        #Gets name of channels
        channel_list = []
        for x in xml[0][0].findall('Channel'):
            #print(x[0].text)
            channel_list.append(x[0].text)   
        #print(channel_list)

        connection.disconnect()

        return channel_list
    
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    channel_list = asyncio.run(get_channels_from_qtm())
    return channel_list
