import asyncio
from tkinter import Y
import qtm
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import multiprocessing
import xml.etree.ElementTree as ET

# This script is to be used in conjunction with the Analog_Testing Project in QTM.
# First open QTM. When prompted for the filename, choose Analog_Testing.

def real_time_stream(q_analog, q_frame):
    # Creating the main asynchronous function 
    async def initiate():
        # Connect to the QTM Application. The application should be open.
        connection = await qtm.connect('10.229.96.105', port=22223, version= '1.22')

        if connection is None:
            print("failed to connect")
            return

        async with qtm.TakeControl(connection, 'jd'):
            await connection.new()

        param = await connection.get_parameters(parameters=["analog"])

        #print(param)


        xml = ET.fromstring(param)
        print(xml[0][0][2].text) #Gets number of analog channels

        #print(xml[0][0][5][0].text) #Gets name of channels
        
        #Gets name of channels
        for x in xml[0][0].findall('Channel'):
        #    channel = x.find()
        #    index = 
            print(x[0].text) 

        def on_packet(packet):
            info, data = packet.get_analog()
            if len(data) > 0:
                channels = list(range(len(list(data))))
                analog_out = list(data[0][2][0])
                # Outer loop gets the number of readings per frame, x gives the index, j gives the value
                for x,j in enumerate(analog_out):
                    # Modifies sampling rate
                    if x % 1 == 0:
                        # For each reading, the inner loop takes the x index from each i channel, and compiles it into an i-length list 
                        for i in channels:
                            #print(i)
                            #print(x)
                            if i == 0:
                                data_all_elements = []
                                data_all = list(data[0][2][0])
                                data_all_elements.append(data_all[x])
                            else:
                                #print(data_all_elements)
                                data_all_elements.append(list(data[i][2][0])[x])
                        #print(data_all_elements)
                        q_analog.put(data_all_elements)
                        #print(q_analog.qsize())
                    else:
                        continue
                q_frame.put(packet.framenumber)

        #with open(filename, 'w') as file:
            #    file.write(",".join([str(v) for v in instance]) + "\n")
        await connection.stream_frames(components=['analog'], on_packet = on_packet)
        await asyncio.sleep(9999999999)
        await connection.stream_frames_stop()


    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(initiate())

# Get the number of channels
def get_channel_number():
    # Creating the main asynchronous function 
    async def initiate():
        # Connect to the QTM Application. The application should be open.
        connection = await qtm.connect('10.229.96.105', port=22223, version= '1.22')

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
    channel_list = asyncio.run(initiate())
    return channel_list


#if __name__ == '__main__':
    #q_analog = multiprocessing.Queue()
    #q_frame = multiprocessing.Queue()
    #p1 = multiprocessing.Process(target = real_time_stream, args=(q_analog,q_frame,))
    #p1.daemon = True
    #p1.start()

    #test = get_channel_number()
    #print("there are", len(test) , "channels")