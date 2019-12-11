import arcpy
import requests
import datetime

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Toolbox"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [Tool]


class Tool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Pollution from Skopjepulse.mk"
        self.description = "Takes data for pollution from Skopjsepulse.mk and populates the map with them"
        self.canRunInBackground = False

    def getParameterInfo(self):
        username = arcpy.Parameter(
            displayName="Username for Skopjepulse.mk",
            name="username",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )

        password = arcpy.Parameter(
            displayName="Password",
            name="password",
            datatype="GPStringHidden",
            parameterType="Required",
            direction="Input"
        )

        measure = arcpy.Parameter(
            displayName="Measure",
            name="measure",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )
        
        date = arcpy.Parameter(
            displayName="Date",
            name="date",
            datatype="GPDate",
            parameterType="Required",
            direction="Input"
        )

        date.value = datetime.datetime.now()
        
        measure.filter.type='ValueList'
        measure.filter.list = ['pm10', 'pm25', 'noise', 'temperature', 'humidity', 'so2', 'no2', 'o3']

        params = [username, password, measure, date]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        username = parameters[0]
        password = parameters[1]
        date = parameters[3]

        connection = requests.get('https://skopjepulse.mk/', auth=(username.value, password.value))
        if connection.status_code != 200:
            password.setErrorMessage('Wrong username or password.\nIf you don\'t have an account, make one on Skopjepulse.mk')
        
        date.value = date.value.replace(minute=00, second=00)
        
        return

    def formatDates(self, date):
        return date.isoformat()[0:19] + '%2b01:00'

    def populateMap(self, username, password, measure, date):
        sensors = requests.get('https://skopjepulse.mk/rest/sensor', auth=(username, password))
        stations = {}

        since = date.replace(minute=00, second=00)
        till = since + datetime.timedelta(minutes=15)
        
        #format
        since = self.formatDates(since)
        till = self.formatDates(till)

        for sensor in sensors.json():
            id = sensor['sensorId']
            status = sensor['status']

            stations[id] = {'status':status}
        
        remove = []
        for key in stations.keys():
            target = 'https://skopjepulse.mk/rest/dataRaw?sensorId={0}&type={1}&from={2}&to={3}'.format(key, measure, since, till)
            request = requests.get(target, auth=(username, password))

            try: log = request.json()[0]
            except: remove.append(key); continue

            date = log['stamp']
            value = log['value']
            position = log['position']
            
            stations[key]['position'] = position
            stations[key]['date'] = date
            stations[key]['value'] = value
        
        #Clean stations
        for key in remove:
            stations.pop(key)
        
        return stations
        
    def execute(self, parameters, messages):
        username = parameters[0].value
        password = parameters[1].value
        measure = parameters[2].value
        date = parameters[3].value
        
        workspace = arcpy.env.workspace
        arcpy.env.overwriteOutput = True
        sr = arcpy.SpatialReference('WGS 1984')
        arcpy.env.outputCoordinateSystem = sr

        stations = self.populateMap(username, password, measure, date)

        name = '{0}Pollution_{1}'.format(measure, date.isoformat()[:19]).replace(':', '').replace('-', '')
        
        arcpy.AddMessage(name)
        arcpy.CreateFeatureclass_management(workspace, name, 'POINT', spatial_reference = sr) #Status
        arcpy.AddField_management(name, measure, 'FLOAT')
        arcpy.AddField_management(name, 'status', 'TEXT')
        arcpy.AddField_management(name, 'id', 'TEXT')

        cursor = arcpy.da.InsertCursor(name, '*')

        for count, (key, station) in enumerate(stations.items()):
            id = key
            position = stations[key]['position']
            value = stations[key]['value']
            status = stations[key]['status']
            
            value = float(value)
            latitude, longtitude = position.split(',')
            latitude, longtitude = float(latitude), float(longtitude)

            point = arcpy.Point(longtitude, latitude)
            row = [count, point, value, status, id]

            cursor.insertRow(row)

        del cursor
        arcpy.AddXY_management(name)

        mxd = arcpy.mapping.MapDocument('CURRENT')
        df = arcpy.mapping.ListDataFrames(mxd)[0]

        layer = arcpy.mapping.Layer(name)
        arcpy.mapping.AddLayer(df, layer, 'TOP')

        layer = arcpy.mapping.ListLayers(mxd, name)[0]
        layer.labelClasses[0].expression = '[{0}]'.format(measure)
        layer.showLabels = True

        arcpy.RefreshActiveView()

        return
