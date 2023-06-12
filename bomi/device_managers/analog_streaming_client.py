import asyncio
import qtm
import xml.etree.ElementTree as ET

# This script is to be used in conjunction with the Analog_Testing Project in QTM.
# First open QTM. When prompted for the filename, choose Analog_Testing.

def real_time_stream(q_analog, q_frame, IPaddress: str, port: int, version: str):
    # Creating the main asynchronous function 
    def on_packet(packet): #recieves data from qtm
            info, data = packet.get_analog() #get analog data from qtm 
            if len(data) > 0:
                channels = list(range(len(list(data))))
                analog_out = list(data[0][2][0])
                # Outer loop gets the number of readings per frame, x gives the index, j gives the value
                for x,j in enumerate(analog_out):
                    # Modifies sampling rate
                    if x % 1 == 0:
                        # For each reading, the inner loop takes the x index from each i channel, and compiles it into an i-length list 
                        for i in channels:
                            if i == 0:
                                data_all_elements = []
                                data_all = list(data[0][2][0])
                                data_all_elements.append(data_all[x])
                            else:
                                data_all_elements.append(list(data[i][2][0])[x])
                        q_analog.put(data_all_elements)
                    else:
                        continue
                q_frame.put(packet.framenumber)
            
    async def initiate(): #Defining Coroutine
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

        print('running in analog_streaming_client')
        await connection.stream_frames(components=['analog'], on_packet = on_packet)
        await asyncio.sleep(2)

        print('stopping in analog_streaming_client')
        await connection.stream_frames_stop()

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Set the policy to prevent "Event loop is closed" error on Windows - https://github.com/encode/httpx/issues/914
        #An event loop policy is a global object used to get and set the current event loop, as well as create new event loops. 
        #set_event_loop_policy: Set the current process-wide policy to policy. If policy is set to None, the default policy is restored.
    
    print('waiting to run in analog_streaming_client')
    asyncio.run(initiate()) #running Coroutine

# Get the number of channels
def get_channel_number(IPaddress: str, port: int, version: str):
    # Creating the main asynchronous function 
    async def initiate():
        # Connect to the QTM Application. The application should be open.
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