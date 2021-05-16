# -*- coding: utf-8 -*-
"""Controllers for the python.venus application."""
from tg.configuration import config
from tg import request
from sqlalchemy import asc, desc, text
import math
from sqlalchemy import create_engine
engine = create_engine(config['sqlalchemy.url'])
from jqgrid2.model import DBSession
import requests
import json
from base64 import b64encode, b64decode
from sqlalchemy import or_

class DynamicFilter(object):

    def __init__(self, sord=None,sidx=None,query=None, model_class=None, filter_condition=None):
        self.query = query
        self.model_class = model_class
        self.filter_condition = filter_condition
        self.sord=sord
        self.sidx=sidx
        self.sidxArray = sidx.split(",")

    def get_query(self):
        '''
        Returns query with all the objects
        :return:
        '''

        if len(self.sidxArray)==1:
            if not self.query:
                if self.sord == "asc":
                    self.query = DBSession.query(self.model_class).order_by(asc(self.sidx))
                else:
                    self.query = DBSession.query(self.model_class).order_by(desc(self.sidx))
        else:
            if not self.query:
                if self.sord == "asc":
                    self.query = DBSession.query(self.model_class).order_by(asc(self.sidxArray[0])).order_by(asc(self.sidxArray[1]))
                else:
                    self.query = DBSession.query(self.model_class).order_by(desc(self.sidxArray[0])).order_by(asc(self.sidxArray[1]))
        #self.query = self.session.query(self.model_class)

        return self.query

    def filter_query(self, query, filter_condition):

        '''
        Return filtered queryset based on condition.
        :param query: takes query
        :param filter_condition: Its a list, ie: [(key,operator,value)]
        operator list:
            eq for ==
            lt for <
            ge for >=
            in for in_
            like for like
            value could be list or a string
        :return: queryset

        '''
        if query is None:
            query = self.get_query()

        model_class =  self.model_class  # returns the query's Model
        for raw in filter_condition:
            try:
                key, op, value = raw
            except ValueError:
                raise Exception('Invalid filter: %s' % raw)
            column = getattr(model_class, key, None)
            if not column:
                raise Exception('Invalid filter column: %s' % key)
            if op == 'in':
                if isinstance(value, list):
                    filt = column.in_(value)
                else:
                    filt = column.in_(value.split(','))
            else:
                try:
                    attr = list(filter(lambda e: hasattr(column, e % op),['%s', '%s_', '__%s__']))[0] % op
                except IndexError:
                    raise Exception('Invalid filter operator: %s' % op)
                if value == 'null':
                    value = None
                filt = getattr(column, attr)(value)
            query = query.filter(filt)
        return query

    def return_query(self):
        return self.filter_query(self.get_query(), self.filter_condition)

class jqgridDataGrabber(object):

    def __init__(self, currentmodel,key,filter,kwargs):
        self.model = currentmodel
        self.indexkey = key
        self.filter = filter
        self.kw=kwargs


    def loadGrid(self):
        if self.kw['_search']=='false':
            selectedpage = int(self.kw['page'])
            dynamic_filtered_query_class = DynamicFilter(self.kw['sord'],self.kw['sidx'],query=None, model_class=self.model,filter_condition=self.filter)
            themodel = dynamic_filtered_query_class.return_query()
            pageIndex = int(self.kw['page']) - 1
            pageSize = int(self.kw['rows'])
            totalRecords = themodel.count()
            #print("Total Records:{}".format(totalRecords))
            totalPages = int(math.ceil(totalRecords / float(pageSize)))
            offset = (pageIndex) * pageSize
            window = themodel.offset(offset).limit(pageSize)
            records=[]
            fields=[]
            for rw in window:
                for columnlist in rw.__table__.columns:
                    #print(column.name)
                    column = getattr(rw, columnlist.name)
                    toc = str(type(column))
                    #print("loading: {} to {} ".format(columnlist.name,toc))

                    if column is not None:
                        value=(column) #unicode
                        if toc == "<type 'bool'>":
                            if column is False:
                                value="0"
                            else:
                                value="1"
                        if toc == "<type 'datetime.datetime'>":
                            value = column.strftime("%Y-%m-%d")

                    else:
                        if toc == "<type 'str'>":
                            value = u""
                        if toc == "<type 'unicode'>":
                            value=u""
                        if toc == "<type 'datetime.datetime'>":
                            value=""
                        else:
                            value="0"
                            #print("loading: {} to {} type:{}".format(str(column), value, str(type(column))))

                    fields.append(value)
                records.append({self.indexkey:  str(getattr(rw, self.indexkey)), 'cell': fields})
                fields=[]
            #print(records)
        else:
            selectedpage = int(self.kw['page']) # 0; # get the requested page
            limit =  int(self.kw['rows']) # 50; #get how many rows we want to have into the grid
            sidx = self.kw['sidx'] #1; #get index row - i.e. user click to sort
            sord = self.kw['sord'] #"asc"; #// get the direction
            #print ("page:{} limit:{} sidx:{} sord:{}".format(selectedpage,limit,sidx,sord))
            operations={}
            operations['eq']="= '{}'"  # Equal
            operations['ne'] = "<> '{}'"  # Not Equal
            operations['lt'] = "< '{}'"  # Less Than
            operations['le'] = "<= '{}'"  # Less than or equal
            operations['gt'] = "> '{}'"  # Greater than
            operations['ge'] = ">= '{}'"  # Greater or equal
            operations['bw'] = "like '{}%'"  # Begins With
            operations['bn'] = "not like '{}%'"  # Does not begin with
            operations['in'] = "in ('{}')" # In
            operations['ni'] = "not in ('{}')"  # Not in
            operations['ew'] = "like '%{}'"  # Ends with
            operations['en'] = "not like '%{}'"  # Does not end with
            operations['cn'] = "like '%{}%'"  # Contains
            operations['nc'] = "not like '%{}%'"  # Does not contain
            operations['nu'] = "is null"  # is Null
            operations['nn'] = "is not null" # is not Null
            #value=MySQLdb.escape_string(self.kw['searchString'])
            if self.kw['filters'] != "":
                filter_json = json.loads(self.kw['filters'])
                i = 0
                for item in filter_json['rules']:
                    if i == 0:
                        i += 1
                        where = "WHERE {} {}".format(item['field'], operations['cn'].format(item['data']))
                    else:
                        where += "AND {} {}".format(item['field'], operations['cn'].format(item['data']))
            else:
                where = "WHERE {} {}".format(self.kw['searchField'],operations[self.kw['searchOper']].format(self.kw['searchString']))
            if len(self.filter)>0:
                where = where + " and " + self.filter[0][0] + operations[self.filter[0][1]].format(self.filter[0][2])

            fields=self.model.__table__.columns
            myfields=""
            ndx=0
            pointer=0
            for item in fields:
                if item==self.indexkey:
                   ndx=pointer
                pointer=pointer+1
                myfields=myfields+item.name+","
            myfields=myfields[:-1]
            sql = "SELECT "+myfields+ " FROM "+self.model.__tablename__+" "+ where +" ORDER BY " + sidx + " "+ sord
            query = text(sql)
            result = engine.execute(query)
            data = result.fetchall()
            if limit<0:
                limit=0
            start=(limit*selectedpage)-limit
            if start < 0:
                start=0
            totalRecords=0
            records = []
            pos=0
            for row in data:
                fields=[]
                for item in row:
                    fields.append((item))#unicode
                key=str(fields[ndx])
                if pos>=start and pos<=start+limit-1:
                    records.append({self.indexkey: key, 'cell': fields})
                totalRecords=totalRecords+1
                pos=pos+1

            if totalRecords>0:
                totalPages=int(math.ceil(totalRecords / float(limit)))
            else:
                totalPages=0

            if selectedpage>totalPages:
                selectedpage=totalPages

        return dict(total=totalPages, page=selectedpage, records=totalRecords, rows=records)

    def updateGrid(self):
        if self.kw['oper'] == "edit":
            #print("edit")
            # print("id:{}".format(self.kw['id']))
            # for key, value in self.kw.items():
            #     print "%s = %s" % (key, value)

            my_filters = {self.indexkey: self.kw['id']}
            query = DBSession.query(self.model)

            for attr, value in my_filters.items():
                query = query.filter(getattr(self.model, attr) == value)
            item=query.first()
            if item is not None:
                #print("None Edit")
                for column in item.__table__.columns:
                    if column.name!=self.indexkey:

                        if column.name in self.kw:
                            if str(column.type) == "BOOLEAN":
                                newvalue = True if self.kw[column.name]=="True" else False
                            else:
                                newvalue =self.kw[column.name]
                            #print("updating: {} to {} type:{}".format(column.name, self.kw[column.name],str(column.type)))
                            setattr(item,column.name,newvalue)
                DBSession.flush()
        if self.kw['oper'] == "add":
            item = self.model()
            #print("add")
            for column in item.__table__.columns:
                if column.name in self.kw:
                    #print("{}={}".format(str(column.name),str(self.kw[column.name])))
                    if (self.indexkey==column.name):
                        pass
                    else:
                        setattr(item, column.name, self.kw[column.name])

            DBSession.add(item)
            DBSession.flush()
        if self.kw['oper'] == "del":
            my_filters = {self.indexkey: self.kw['id']}
            query = DBSession.query(self.model)
            for attr, value in my_filters.items():
                query = query.filter(getattr(self.model, attr) == value)
            item=query.first()
            if item is not None:
                DBSession.delete(item)
                DBSession.flush()
        return dict(error="")