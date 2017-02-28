#! /usr/bin/env python2.5
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ElementTree
import indigo

""" This module receives the XML data as a string and returns a dictionary (finalDict)
    which contains key/value pairs which represent the source XML.
    
    Credit for XmlDictConfig(): http://code.activestate.com/recipes/410469-xml-as-dictionary/
    Credit for updateShim(): http://stackoverflow.com/users/3871670/adam-clark
    Credit for flatten_dict(): http://codereview.stackexchange.com/users/1659/winston-ewert
    """


class XmlDictConfig(dict):
    def __init__(self, parent_element):
        if parent_element.items():
            self.updateShim(dict(parent_element.items()))

        for element in parent_element:
            if len(element):
                aDict = XmlDictConfig(element)
                
                if element.items():
                    aDict.updateShim(dict(element.items()))
                self.updateShim({element.tag: aDict})
                
            elif element.items():
                self.updateShim({element.tag: element.text}) # This line added to handle when value and attribs are both present.
                elementTagAttribs = element.tag + u'_A_t_t_r_i_b_s' # This line added to create a unique element.tag for attribs.
                self.updateShim({elementTagAttribs: dict(element.items())}) # This line modded to use new element.tag + '_Attribs'.
            else:
                self.updateShim({element.tag: element.text}) # WAS: _self.updateShim({element.tag: element.text.strip()})_ with strip(), the function will choke on some XML. 'NoneType' object has no attribute 'strip'.

    def updateShim(self, aDict):
        for key in aDict.keys():
            if key in self:
                value = self.pop(key)
                
                if type(value) is not list:
                    listOfDicts = []
                    listOfDicts.append(value)
                    listOfDicts.append(aDict[key])
                    self.update({key: listOfDicts})
                else:
                    value.append(aDict[key])
                    self.update({key: value})
            else:
                self.update(aDict)
                    
def flatten_dict(d):
    def expand(key, value):
        if isinstance(value, dict):
            return [ (key + '_' + k, v) for k, v in flatten_dict(value).items() ]
        else:
            return [ (key, value) ]
            
    items = [ item for k, v in d.items() for item in expand(k, v) ]
    return dict(items)

def iterateMain(root):
    
    try:
        root = ElementTree.fromstring(root)
        xmlDict = XmlDictConfig(root)
        flatxmlDict = flatten_dict(xmlDict)
        finalDict = {}

        for (key, value) in flatxmlDict.items():

            finalDict[key] = value
    
            # See if any 'value' is another list. These lists may contain information for more
            # values we want--for example, when there are multiple instances of the same tag
            # (with different attributes or values.)
            if isinstance(value, list):
        
                # If any lists found contain a dictionary, iterate over that dictionary and make
                # more key/value pairs. Also, this may need more counters depending on the 
                # depth of the source XML data.  Right now it only goes so deep.
                counter = 1        
                for valueItem in value:
        
                    if isinstance(valueItem, dict):
                        for (valueKey1, value1) in valueItem.items():
                            newKey1 = u'%s_%s_%s' % (key, counter, valueKey1)
                            finalDict[newKey1] = value1
                    
                            if isinstance(value1, dict):
                                for (valueKey2, value2) in value1.items():
                                    newKey2 = u'%s_%s_%s_%s' % (key, counter, valueKey1, valueKey2)
                                    finalDict[newKey2] = value2

                                if isinstance(value2, dict):
                                    for (valueKey3, value3) in value2.items():
                                        newKey3 = u'%s_%s_%s_%s' % (key, counter, valueKey2, valueKey3)
                                        finalDict[newKey3] = value3
                    counter += 1

        # We may be left with values that contain lists of duplicates. Take the first one
        # and leave the rest.
        for (key, value) in finalDict.items():
            if isinstance(value, list):
                finalDict[key] = value[0]

        # Find any remaining dicts, and delete them. This operation should ultimately
        # determine if all of the dict items have already been pulled out to ensure that we
        # don't lose anything.
        for (key, value) in finalDict.items():
            if isinstance(value, dict):
            
                del finalDict[key]
    
        # Now that we're done, get rid of the placeholder Attribs tag component since we don't
        # need it anymore.        
        for (key,value) in finalDict.items():
            del finalDict[key]
            key = key.replace(u'_A_t_t_r_i_b_s',"")
            finalDict[key] = value
    
    except:
        indigo.server.log(u'There was an parse error. Check XML source.')
        finalDict = {'Response':'Parse error. Check XML source.'}
    
    return finalDict
