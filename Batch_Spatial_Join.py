"""
Automated_spatial_join.py

Purpose: This is a script for a ArcGIS Pro custom toolbox containing
         a tool which automates the spatial join process. The funtions of the
         custom tool include:
              - change the spatial reference of the join layers to match the
                      target layer
              - delete fields that are undesired in the final output
              - changes the name of nonunique fields to make them unique
              - spatial join any number of polygon layers to a target layer

Author: Jason Greenstein
Date: September 26, 2019
"""
import arcpy


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Toolbox"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [CoralGeoJoin]


class CoralGeoJoin(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "CoralGeoJoin"
        self.description = "Joins multiple polygon features to a target point feature."
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""

        param0 = arcpy.Parameter(
            displayName="Input Workspace",
            name="workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Target Feature",
            name="corals_input",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Output Feature Class",
            name="corals_output",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")


        param3 = arcpy.Parameter(
            displayName="Fields to delete",
            name="fields_to_delete",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            multiValue=True)

        param3.filter.type = "ValueList"


        param4 = arcpy.Parameter(
            displayName="Update Fields",
            name="update_fields",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")

        param4.filter.type = "ValueList"
        param4.filter.list = ["Yes","No"]

        parameters = [param0,param1,param2,param3,param4]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        workspace = parameters[0]
        #arcpy.env.workspace = workspace.valueAsText
        delete_list = parameters[3]
        fields = []
        if workspace.altered:
            arcpy.env.workspace = workspace.valueAsText
            features = arcpy.ListFeatureClasses(feature_type='Polygon')
            for fc in features:
                lFields = arcpy.ListFields(fc)
                for fd in lFields:
                    dict = {}
                    if (fd.name != 'OBJECTID' and
                        fd.name != 'Shape' and
                        fd.name != 'Shape_Length' and
                        fd.name != 'Shape_Area'):
                        dict[fc] = fd.name
                        for (key,value) in dict.items():
                            key_string = key + ':' + value
                            fields.append(key_string)

        delete_list.filter.list = fields
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        try:
            import arcpy, os, sys, traceback

            workspace = parameters[0].valueAsText
            corals_input = parameters[1].valueAsText
            corals_output = parameters[2].valueAsText
            fields_to_delete = parameters[3].valueAsText
            update_fields = parameters[4].valueAsText


            arcpy.env.workspace = workspace
            arcpy.env.overwriteOutput = True
            arcpy.env.scratchWorkspace = workspace
            arcpy.env.extent = corals_input

            features = arcpy.ListFeatureClasses(feature_type='Polygon')
            numFeatures = len(features)


            # Error: ArcGIS Spatial Analyst extension not Available, script will end
            if arcpy.CheckExtension("Spatial") != "Available":
                arcpy.AddError("ArcGIS Spatial Analyst extension is not available")
                sys.exit()

            # Error: workspace contains no polygon features, script will end
            if numFeatures == 0:
                arcpy.AddError("There are no polygon features in the workspace.")
                sys.exit()


            coral_spatialReference = arcpy.Describe(corals_input).spatialReference
            coral_spatialReference_WKID = coral_spatialReference.factoryCode

            joinFields_str = []   #list of string fields for UpdateCursor


            def change_spatial_reference(feature):
                """"projects the target feature's spatial reference to match the join feature's"""
                join_spatialReference = arcpy.Describe(feature).spatialReference
                join_spatialReference_WKID = join_spatialReference.factoryCode
                if coral_spatialReference_WKID != join_spatialReference_WKID:
                    feature_project = os.path.join(arcpy.env.scratchGDB, os.path.split(fc)[1]) +"_"
                    arcpy.management.Project(feature, feature_project, coral_spatialReference_WKID)
                    return feature_project
                else:
                    return feature


            def delete_join_fields(feature,delete = []):
                """deletes user specified fields in target feature"""
                fields =  arcpy.ListFields(feature)
                if delete is None:
                    return feature
                else:
                    for field in fields:
                        field_name = field.name
                        if field_name in delete:
                            arcpy.DeleteField_management(feature, field_name)
                return feature



            def change_join_field_names(feature):
                """ renames join field names"""
                fields =  arcpy.ListFields(feature)
                for field in fields:
                    field_name = field.name
                    if (field_name != 'OBJECTID' and
                        field_name != 'Shape' and
                        field_name != 'Shape_Length' and
                        field_name != 'Shape_Area'):

                        feature_name = os.path.split(feature)[1]
                        newName = feature_name + field_name
                        # catch field name over 31 characters
                        if len(newName) > 31:
                            extra_characters = len(newName) - 30
                            newName = newName[extra_characters:]
                        arcpy.AlterField_management(feature,field_name,newName,newName)

                        if field.type =="String":
                            joinFields_str.append(newName)
                return feature


            def coral_geo_join(coral, feature):
                """spatially join features, creates a scratch file for each join"""
                scratch_name = arcpy.CreateScratchName("tempCoralJoin",
                                                        data_type="FeatureClass",
                                                        workspace=arcpy.env.scratchGDB)

                arcpy.analysis.SpatialJoin(coral, feature, scratch_name)
                arcpy.DeleteField_management(scratch_name, ["Join_Count", "TARGET_FID"])
                return scratch_name



            #Converts shapefiles into gdb features
            if '.gdb' not in workspace[-4:]:
                for shapefile in features:
                    if arcpy.Describe(shapefile).shapeType == 'Polygon':
                        outFeatureClass = os.path.join(arcpy.env.scratchGDB, os.path.splitext(shapefile)[0])
                        arcpy.CopyFeatures_management(shapefile, outFeatureClass)
                # updates workspace and list of features
                arcpy.env.workspace = arcpy.env.scratchGDB
                features = arcpy.ListFeatureClasses(feature_type='Polygon')


            i = 1
            #Spatial Join all geomorphic features to corals
            for counter,fc in enumerate(features, start=1):
                if arcpy.Describe(fc).shapetype == 'Polygon':
                    # catches if CopyFeatures_managment already run from copying shapefiles
                    if '.gdb' in workspace[-4:]:
                        feature_copy = os.path.join(arcpy.env.scratchGDB, os.path.split(fc)[1])
                        arcpy.CopyFeatures_management(fc,feature_copy)
                        fc = feature_copy

                    change_spatial_reference(fc)
                    arcpy.AddMessage('change spatial reference complete')

                    delete_join_fields(fc,fields_to_delete)
                    change_join_field_names(fc)

                    #clean_geomorph_layers(fc)
                    arcpy.AddMessage('clean complete')

                    corals_input = coral_geo_join(corals_input, fc)



                    #tool message telling the user how many features have been joined
                    arcpy.AddMessage(f"{counter}/{numFeatures} joins complete")


            #copies last spatial join output to workspace
            arcpy.CopyFeatures_management(corals_input, corals_output)

            #updates string fields to short values
            if update_fields == "Yes":
                arcpy.AddMessage("---------------")
                arcpy.AddMessage("---------------")
                arcpy.AddMessage("Data Dictionary")
                arcpy.AddMessage("---------------")
                for field in joinFields_str:
                    string_fields = []
                    string_fields.append(field)
                    with arcpy.da.SearchCursor(corals_output, string_fields) as cursor:
                        unique_attributes =[]
                        for row in cursor:
                            if row[0] not in unique_attributes:
                                unique_attributes.append(row[0])
                            if len(unique_attributes) > 6:
                                print(f"{field} has more than 6 unique attributes. {field} removed from list ")
                                string_fields = []
                                break
                        del cursor

                    if len(string_fields) != 0:
                        attributes = {}
                        i = 1
                        with arcpy.da.UpdateCursor(corals_output, string_fields) as cursor:
                            for row in cursor:
                                if row[0] == None:
                                    attributes[row[0]] = 0
                                    row[0] = '0'
                                elif row[0] not in attributes and row[0] != None:
                                    attributes[row[0]] = i
                                    i += 1
                                    row[0] = attributes[row[0]]
                                else:
                                    row[0] = attributes[row[0]]
                                cursor.updateRow(row)

                        arcpy.AddMessage(field)
                        for (key,value) in attributes.items():
                            arcpy.AddMessage("     " + f"{key}:{value}")
                        arcpy.AddMessage("---------------")
                arcpy.AddMessage("---------------")
                arcpy.AddMessage("---------------")



        # Return geoprocessing specific errors
        except arcpy.ExecuteError:
            print(arcpy.GetMessages(2))
            arcpy.AddError(arcpy.GetMessages(2))

        except:
            # Get the traceback object
            tb = sys.exc_info()[2]
            tbinfo = traceback.format_tb(tb)[0]

            # Concatenate information together concerning the error into a message string
            pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
            msgs = "ArcPy ERRORS:\n" + arcpy.GetMessages(2) + "\n"

            # Return python error messages for use in script tool or Python window
            arcpy.AddError(pymsg)
            arcpy.AddError(msgs)

            # Print Python error messages for use in Python / Python window
            print(pymsg)
            print(msgs)


        finally:
            # delete scratch files
            arcpy.env.workspace = arcpy.env.scratchGDB

            scratch_features = arcpy.ListFeatureClasses()
            for scratchFeature in scratch_features:
                arcpy.Delete_management(scratchFeature)


        corals_output = None

        return
