import PodSixNet.Channel
import PodSixNet.Server

import shutil
import socket
import os
import time
import pickle
import tkinter as tk
import tkinter.filedialog
from tkinter import ttk
import threading
import queue
import datetime

class ClientChannel(PodSixNet.Channel.Channel):
    def __init__(self, *args, **kwargs):
        PodSixNet.Channel.Channel.__init__(self, *args, **kwargs)
        self.nickname= None
        
    def Close(self):
        global server
        if self.nickname is not None:
            server.queue.put({'type': 'log', 'data': self.nickname+ ' has disconnected', 'end': ''})
            for c in server.clientnames:
                if c['nick']== self.nickname:
                    server.clientnames.remove(c)

            server.clientlist.remove(self)
            server.numclients-= 1
            server.queue.put({'type': 'numclients', 'data': server.numclients})
            server.queue.put({'type': 'clientnames', 'data':server.clientnames})
            
        count= 0
        for cand in server.testingcandidates[:]:
            if cand.client== self.nickname:
                server.testingcandidates.remove(cand)
                count+= 1
                cand.progress= 'untested'
                server.waitingcandidates.insert(0, (cand, time.time()))
                server.candidates.insert(0, cand)

        if count!= 0:
            server.queue.put({'type': 'log', 'data':', unreserved '+ str(count)+ ' candidates'})
        
        with open(os.getcwd()+'\\data\\serverdata.pickle', 'wb') as w:
            pickle.dump({'candidates':server.candidates,
                         'testingcandidates':server.testingcandidates,
                         'loadedfiles': server.loadedfiles,
                         'waiting': server.waitingcandidates}, w)
        

    def Network(self, data):
        pass
    def Network_connected(self, data):
        pass
    
    def Network_nickname(self, data):
        global server
        if data['nick'] is not None:
            server.numclients+= 1
            server.clientlist.append(self)
            server.clientnames.append(data)
            server.queue.put({'type': 'numclients', 'data': server.numclients})
            server.queue.put({'type': 'clientnames', 'data':server.clientnames})
            self.nickname= data['nick']
            server.queue.put({'type': 'log', 'data':'New connection: '+ str(self.nickname)})

        clientcand= []
        for (cand, _) in server.waitingcandidates[:]: #check to see if this connection had any previously reserved candidates and give them to it.
            if cand.client== data['nick']:
                server.waitingcandidates.remove((cand, _))
                cand.progress= 'testing'
                server.testingcandidates.append(cand)
                clientcand.append(cand.data)
        if len(clientcand)!= 0:
            server.queue.put({'type': 'log', 'data':data['nick']+ ' was sent '+ str(len(clientcand))+ ' previous reserved candidates'})
            self.Send({'action': 'newcandidates', 'data': clientcand})

    def Network_clienterror(self, data):
        global server
        server.queue.put({'type': 'log', 'data': str(self.nickname)+ ': Error: '+ str(data['data'])})
    def Network_getload(self, data):
        if self.nickname!= None:
            global server
        
            candidates= server.getCandidates(data['amount'], self.nickname)
            self.Send({'action': 'newcandidates', 'data': candidates})

        
    def Network_completetest(self, data):
        global server
        if 'is prime' in data['data']:
            s= data['data'].split(' ')
            send= s[0]+ ' '+ s[1]+ ' '+ s[2]
            server.queue.put({'type': 'log', 'data': self.nickname+ ': '+send})
        

        found= False
        
        for cand in server.testingcandidates[:]:
            if cand.data== data['data'].split(' ')[0]:
                found= True
                with open('lresults_'+cand.file.replace('.txt', '').split('\\')[-1]+'.txt', 'a') as w:
                    w.write(data['data'].replace('\n', '')+ '\n')
                    
                server.testingcandidates.remove(cand)
        if not found:
            for cand in server.candidates[:]:
                if cand.data== data['data'].split(' ')[0]:
                    found= True
                    with open('lresults_'+cand.file.replace('.txt', '').split('\\')[-1]+'.txt', 'a') as w:
                        w.write(data['data'].replace('\n', '')+ '\n')
                    
                    server.candidates.remove(cand)

        with open(os.getcwd()+'\\data\\serverdata.pickle', 'wb') as w:
            pickle.dump({'candidates':server.candidates,
                         'testingcandidates':server.testingcandidates,
                         'loadedfiles': server.loadedfiles,
                         'waiting': server.waitingcandidates}, w)
        if found:
            if self.nickname== None:
                server.queue.put({'type': 'result', 'data': data['data'], 'who': '?'})
            else:
                server.queue.put({'type': 'result', 'data': data['data'], 'who': self.nickname})

    def Network_pingsuccess(self, data):
        global server
        server.queue.put({'type': 'pingsuccess', 'data': self.nickname})

    def Network_ping(self, data):
        self.Send({'action': 'pingsuccess'})
        
class LLRServer(PodSixNet.Server.Server):

    channelClass= ClientChannel
    def __init__(self, *args, **kwargs):
        PodSixNet.Server.Server.__init__(self, *args, **kwargs)
        self.clientlist= []
        self.testingcandidates= []
        self.waitingcandidates= []
        self.clientnames= []
        self.loc = os.getcwd()+ '/candidates'
        self.candidates= []
        self.numclients= 0
        self.queue= queue.Queue()

        self.queue.put({'type': 'log', 'data':'loading saved server files', 'end': ''})
        try:
            data= pickle.load(open(os.getcwd()+'\\data\\serverdata.pickle', 'rb'))
        except FileNotFoundError:
            self.queue.put({'type': 'log', 'data':', found 0 candidates'})
            self.loadedfiles= []
        else:
            self.candidates= data['candidates']
            self.queue.put({'type': 'log', 'data': ', found '+ str(len(self.candidates))+ ' candidates'})
            self.testingcandidates= data['testingcandidates']
            self.loadedfiles= data['loadedfiles']
            self.waitingcandidates= data['waiting']

        if len(self.testingcandidates) > 0:
            self.queue.put({'type': 'log',
                            'data':'found '+ str(len(self.testingcandidates))+
                            ' candidates in progress, marking as untested'})
            for candidate in self.testingcandidates[:]:
                self.testingcandidates.remove(candidate)
                candidate.progress= 'untested'
                candidate.client= None
                self.candidates.insert(0, candidate)
                
        self.loadfiles()
        self.queue.put({'type': 'total', 'data': len(self.candidates)+len(self.waitingcandidates)})
        
        self.queue.put({'type': 'log', 'data':'data files loaded'})
        

    def loadfiles(self):
        files= [] #regular .npg format files
        wwfiles= [] #.ww format files in (b-koff)*b^(b+noff) +/- 1 format
        newcandidates= 0
        self.queue.put({'type': 'log', 'data': 'loading raw llr files...'})
        for file in os.listdir(self.loc):
            if file.endswith('.txt') and os.getcwd()+ '\\candidates\\'+ file not in self.loadedfiles:
                files.append(os.getcwd()+ '\\candidates\\'+ file)
            if file.endswith('.ww') and os.getcwd()+ '\\candidates\\'+ file not in self.loadedfiles:
                wwfiles.append(os.getcwd()+ '\\candidates\\'+ file)
        self.queue.put({'type': 'log', 'data': 'found '+ str(len(files))+ ' new data files'})

        for file in files:
            filedata= open(file, 'r').readlines()
            self.queue.put({'type': 'log',
                            'data': 'opening '+ str(file.split('\\')[-1])+ ', found '+ str(len(filedata)-1)+' candidates'})
            newcandidates+= (len(filedata)-1)
            for candidate in filedata[1:]:
                z= candidate.replace('\n', '').split(' ')
                m= z[0]+ '*2^'+ z[1]+ '-1'
                self.candidates.append(Candidate(m, file))

        for file in wwfiles:
            filedata= open(file, 'r').readlines()
            self.queue.put({'type': 'log',
                            'data': 'opening '+ str(file.split('\\')[-1])+ ', found '+ str(len(filedata)-1)+' candidates'})
            newcandidates+= (len(filedata)-1)
            _, _,koff, noff, sign = filedata[0].replace('\n', '').split(':')
            for candidate in filedata[1:]:
                b= int(candidate.replace('\n', '').split(' ')[0])
                k= b+ int(koff)
                n= b+ int(noff)
                cand= str(k)+'*'+str(b)+'^'+str(n)+sign+'1'
                self.candidates.append(Candidate(cand, file))
        self.loadedfiles+= files + wwfiles

        with open(os.getcwd()+'\\data\\serverdata.pickle', 'wb') as w:
            pickle.dump({'candidates':self.candidates,
                         'testingcandidates':self.testingcandidates,
                         'loadedfiles': self.loadedfiles,
                         'waiting': self.waitingcandidates}, w)
        
        return newcandidates
    def Connected(self, channel, addr):
        #channel.Network_connected(5)
        channel.Send({'action': 'welcome', 'msg': 'Connected Successfully'})
        #self.channels.append(channel)
        
    def getCandidates(self, amount, nickname):
        z= []
        f= []
        for cand in self.candidates[:amount]:
            cand.client= nickname
            cand.progress= 'testing'
            z.append(cand)
            f.append(cand.data)
            
        self.candidates= self.candidates[amount:]
        self.testingcandidates+= z

        
        with open(os.getcwd()+'\\data\\serverdata.pickle', 'wb') as w:
            pickle.dump({'candidates':self.candidates,
                         'testingcandidates':self.testingcandidates,
                         'loadedfiles': self.loadedfiles,
                         'waiting': self.waitingcandidates}, w)

        return f
    def ping(self):
        for client in self.clientlist:
            client.Send({'action': 'ping'})

    def checkwait(self):
        for (cand, timestamp) in self.waitingcandidates[:]:
            if time.time()- timestamp > 60*60*6: #6 hours until it gets unreserved
                self.waitingcandidates.remove((cand, timestamp))
                cand.client= None
                cand.progress= 'untested'
                self.candidates.insert(0, cand)

class Candidate():
    def __init__(self, data, file, progress= 'untested'):
        self.data= data
        self.progress= progress
        self.client= None
        self.teststart= -1
        self.file=file
        
    def start(self):
        self.teststart= time.time()
        
class GUI(threading.Thread):

    def __init__(self, q):
        threading.Thread.__init__(self)
        self.queue= queue.Queue()
        self.q= q
        self.start()

    def callback(self):
        self.root.quit()

    def run(self):
        self.clientreserved= {}
        self.clientdata= []
        self.startingcount= 0
        self.pinged= []
        self.logtime= True
        
        self.root = tk.Tk()
        self.root.protocol("WM_DELETE_WINDOW", self.callback)

        self.menubar= ttk.Notebook(self.root)
        self.menubar.grid(row= 0, column= 0, sticky= 'nw')
        
        self.clientmenu= tk.Frame(self.menubar, padx= 5, pady= 5)
        self.llrmenu=    tk.Frame(self.menubar, padx= 5, pady= 5)
        self.logmenu=    tk.Frame(self.menubar, padx= 5, pady= 5)

        self.menubar.add(self.clientmenu, text=' General ')
        self.menubar.add(self.llrmenu,    text='   LLR   ')
        self.menubar.add(self.logmenu,    text='   Log   ')
        
        #GENERAL TAB
        
        self.status1= tk.Label(self.clientmenu, text= 'Server Status:')
        self.status1.grid(row= 0, column= 0, sticky= 'e')
        self.status= tk.Label(self.clientmenu, text= 'Inactive', fg='dark orange')
        self.status.grid(row=0, column= 1, sticky= 'w')

        self.mainframe= tk.LabelFrame(self.clientmenu, borderwidth=0)
        self.mainframe.grid(row= 1, column= 0, columnspan= 2)
        
        self.clientlistframe= tk.LabelFrame(self.mainframe, text= 'Clients: 0')
        self.clientlistframe.grid(row= 1, column= 0, rowspan= 30, padx= 10)
        self.clf= tk.Frame(self.clientlistframe)
        self.clf.grid(row=0, column= 0, padx= 5, pady= 5)
        
        self.clientlist= tk.Text(self.clf, width= 40, height= 20)
        self.clientlist.grid(row= 0, column= 0, pady=5)
        self.clientlist.insert(tk.END, 'Name               Cores      Reserved\n')
        self.clientlist.insert(tk.END, '--------------------------------------\n')
        self.clientlist.config(state= tk.DISABLED)

        self.clientscroll= tk.Scrollbar(self.clf, command= self.clientlist.yview)
        self.clientscroll.grid(row= 0, column=1, sticky= 'ns')
        self.clientlist['yscrollcommand']= self.clientscroll.set

        self.pingframe= tk.LabelFrame(self.mainframe, text= 'Ping')
        self.pingframe.grid(row= 3, column= 1, sticky= 'nwe', padx= 5, pady=5)
        self.pingbtn= tk.Button(self.pingframe, text= 'Ping Clients', padx= 10, command= self.ping)
        self.pingbtn.grid(row= 0, column= 0, sticky= 'n', padx= 5, pady= 5)
        self.pingtext= tk.Label(self.pingframe, text= 'Responses: N/A')
        self.pingtext.grid(row=0, column= 1, padx= 5)

        self.statusframe= tk.LabelFrame(self.mainframe, text= 'Candidates')
        self.statusframe.grid(row=2, column=1, sticky= 'nwe', padx= 5, pady=5)
        self.uploadbtn= tk.Button(self.statusframe, text= 'Upload', padx= 15, command= self.upload)
        self.uploadbtn.grid(row= 0, column= 0, columnspan= 2, padx= 10)
        self.completedtext= tk.Label(self.statusframe, text= 'Completed: 0/0')
        self.completedtext.grid(row=1, column= 0, sticky= 'nswe')
        self.candidatesframe= tk.Label(self.statusframe, text= 'Unreserved: 0')
        self.candidatesframe.grid(row=1, column= 1, sticky= 'nsew')

        self.ipportframe= tk.LabelFrame(self.mainframe, text= 'Start')
        self.ipportframe.grid(row=1, column= 1, sticky= 'nwe', padx=5, pady=5)
        self.iplabel= tk.Label(self.ipportframe, text= 'IP: ')
        self.iplabel.grid(column= 0, row= 0, sticky= 'w')
        self.iptextbox= tk.Entry(self.ipportframe)
        self.iptextbox.grid(row= 0, column=1, columnspan=2)
        self.portlabel= tk.Label(self.ipportframe, text= 'Port: ')
        self.portlabel.grid(column= 0, row= 1)
        self.porttextbox= tk.Entry(self.ipportframe)
        self.porttextbox.grid(row= 1, column=1, columnspan=2)
        self.startbtn= tk.Button(self.ipportframe, text= 'Start', padx= 10, command=self.startserver)
        self.startbtn.grid(row=2, column= 0, columnspan=2, padx= 5, pady= 5)
        self.stopbtn= tk.Button(self.ipportframe, text= 'Stop', padx= 10, command= self.stopserver)
        self.stopbtn.grid(row=2, column= 2, columnspan=2, padx= 5, pady= 5)
        self.stopbtn.config(state= tk.DISABLED)
        
        #LLR TAB
        self.llrtext= tk.Text(self.llrmenu, width= 72, height=24)
        self.llrtext.grid(row=0, column=0)
        self.llrtext.insert(tk.END, ' '*30+ 'LLR Results\n')
        self.llrtext.insert(tk.END, '-'*72+ '\n')
        self.llrtext.config(state=tk.DISABLED)
        self.llrtext.tag_configure('prime', foreground= 'red')
        self.nextcomposite= 3
        self.llrscroll= tk.Scrollbar(self.llrmenu, command= self.llrtext.yview)
        self.llrscroll.grid(row= 0, column=1, sticky= 'ns')
        self.llrtext['yscrollcommand']= self.llrscroll.set

        #LOG TAB
        self.log= tk.Text(self.logmenu, width=72, height= 24)
        self.log.grid(row= 0, column= 0)
        self.logscroll= tk.Scrollbar(self.logmenu, command= self.log.yview)
        self.logscroll.grid(row= 0, column=1, sticky= 'ns')
        self.log['yscrollcommand']= self.logscroll.set
        


        #ROOT
        self.root.after(0, self.update)
        self.root.title('LLR Server')
        self.root.resizable(width=False, height=False)
        self.queue.put({'type': 'log', 'data': 'GUI started'})
        self.root.iconbitmap(os.getcwd()+'\\data\\icon.ico')
        self.root.mainloop()

    def update(self):
        while not self.queue.empty():
            data= self.queue.get()
            if data['type']== 'numclients':
                self.clientlistframe.config(text='Clients: '+ str(data['data']))
                
            if data['type']== 'clientnames': #this is called if a client connects or disconnects
                self.clientdata= data['data']
                self.updateClientTextBox()
                
            if data['type']== 'testingcandidates':
                self.clientreserved= {}
                for candidate in data['data']:
    
                    try:
                        self.clientreserved[candidate.client]+= 1
                    except KeyError:
                        self.clientreserved[candidate.client]= 1
                self.updateClientTextBox()
                #data - testing candidates
                #data2 - untested candidates
                #data3 - waitingcandidates length
                completedtests= self.startingcount- (data['data2']+len(data['data'])+ len(data['data3']))
                self.completedtext.config(text= 'Completed: ' +str(completedtests)+'/'+ str(self.startingcount))
                if data['data2'] > 100:
                    self.candidatesframe.config(text= 'Unreserved: '+ str(data['data2']+len(data['data3'])))
                elif data['data2']== 0:
                    self.candidatesframe.config(fg= 'red', text= 'Unreserved: '+ str(data['data2']+len(data['data3'])))
                else:
                    self.candidatesframe.config(fg= 'orange', text= 'Unreserved: '+ str(data['data2']+len(data['data3'])))
            if data['type']== 'pingsuccess':
                self.queue.put({'type': 'log', 'data': 'Ping recieved from '+ data['data']})
                if data['data'] not in self.pinged:
                    self.pinged.append(data['data'])

            if data['type']== 'total':
                self.startingcount= data['data']
                
            if data['type']== 'result':
                self.llrtext.config(state= tk.NORMAL)
                f= data['data'].replace('  ', ' ').replace(' : ', ': ').replace('e.', 'e').replace('\n', '')
                f= f.replace('s.', 's')
                m= f.split()
                time= datetime.datetime.today().strftime('[%I:%M %p]').replace('[0', '[')
                if 'is prime' in data['data']:
                    f= m[0]+ ' '+ m[1]+ ' '+ m[2]+ ' ('+ m[7]+ m[8]+ ')'
                    f= f.replace(' decimal', '')
                    self.llrtext.insert(str(float(self.nextcomposite)),time+' '+ data['who']+': '+ f+ '\n', 'prime')
                    self.nextcomposite+= 1
                else:
                    m= f.replace('sec.', 's').split(' ')
                    f= m[0]+ ' '+ m[1]+ ' '+ m[2]+ ' '+ m[3]+ ' ('+ m[8]+ m[9]+ ')'

                    self.llrtext.insert(str(float(self.nextcomposite)),time+ ' '+ data['who']+ ': '+f+ '\n')
                    self.llrtext.config(state= tk.DISABLED)

            if data['type']== 'log':
                time= datetime.datetime.today().strftime('[%m/%d/%y %I:%M %p]').replace('[0', '[')
                self.log.config(state= tk.NORMAL)
                try:
                    data['end']
                except KeyError: #no end specified, write a newline
                    if not self.logtime:
                        self.log.insert(tk.END, data['data']+ '\n')
                        self.logtime= True
                    else:
                        self.log.insert(tk.END, time+ ' '+ data['data']+ '\n')
                else:
                    if not self.logtime:
                        self.log.insert(tk.END, data['data']+ data['end'])
                    else:
                        self.log.insert(tk.END, time+ ' '+ data['data']+ data['end'])
                    self.logtime= False
                self.log.config(state= tk.DISABLED)
                    
        self.root.after(200, self.update)
        
    def ping(self, first= True):
        if first:
            self.queue.put({'type': 'log', 'data': 'pinging all clients...'})
            self.t1= time.time()
            self.pinged= []
            self.max= self.clientdata
            ping()
        if time.time()- self.t1 > 8:
            self.pingtext.config(text= 'Responses: N/A')
        else:
            self.pingtext.config(text='Returned: '+ str(len(self.pinged))+ '/'+ str(len(self.max)))
            self.root.after(200, self.ping, False)
        
    def updateClientTextBox(self):
        self.clientlist.config(state= tk.NORMAL)
        self.clientlist.delete(1.0, tk.END)
        self.clientlist.insert(tk.END, 'Name               Cores      Reserved\n')
        self.clientlist.insert(tk.END, '--------------------------------------\n')

        for client in self.clientdata:
            try:
                self.clientreserved[client['nick']]
            except KeyError:
                self.clientreserved[client['nick']]= 0
            self.clientlist.insert(tk.END,
                                    client['nick']+ ' '*(19-len(client['nick']))+
                                    str(client['cores'])+ ' '*(11-len(str(client['cores'])))+
                                    str(self.clientreserved[client['nick']])+ '\n')
        self.clientlist.config(state= tk.DISABLED)
        
    def startserver(self):
        self.q.put({'server': 'on', 'ip': self.iptextbox.get(), 'port': self.porttextbox.get()})

        self.iptextbox.config(state= tk.DISABLED)
        self.porttextbox.config(state= tk.DISABLED)
        self.stopbtn.config(state= tk.NORMAL)
        self.startbtn.config(state=tk.DISABLED)
        self.status.config(text='Running', fg='green')
    def stopserver(self):
        self.q.put({'server': 'off'})
        self.iptextbox.config(state= tk.NORMAL)
        self.porttextbox.config(state= tk.NORMAL)
        self.stopbtn.config(state= tk.DISABLED)
        self.startbtn.config(state=tk.NORMAL)
        self.status.config(text= 'Inactive', fg='dark orange')
    def upload(self):
        global server
        loc= tk.filedialog.askopenfilename()
        if loc!= '':
            shutil.copy2(loc, os.getcwd()+ '\\candidates\\')
        try:
            new= server.loadfiles()
            self.startingcount+= new
        except NameError:
            pass

print('Booting up server')
q= queue.Queue()
gui= GUI(q)
time.sleep(0.15)
try:
    f= open(os.getcwd()+'\\data\\settings.txt', 'r').readlines()
    for line in f:
        line= line.replace(' ', '').replace('\n', '')
        if line.startswith('ip'):
            gui.iptextbox.insert(0, line.split('=')[1])
        if line.startswith('port'):
            gui.porttextbox.insert(0, line.split('=')[1])
except FileNotFoundError:
    pass

def ping():
    global server
    try:
        server.ping()
    except NameError:
        pass
    
c= 0
serverOn= False
waitstopper= time.time()
while True:
    if not q.empty():
        data= q.get()
        if data['server']== 'on':
            serverOn= True
            server= LLRServer(localaddr= (data['ip'], int(data['port'])))
            time.sleep(0.15)
            server.queue.put({'type': 'log', 'data': 'starting server ip: '+
                              gui.iptextbox.get()+ ', port: '+ str(gui.porttextbox.get())})
            gui.queue= server.queue
        if data['server']== 'off':
            server.queue.put({'type': 'log', 'data': 'server closed'})
            serverOn= False
            server.queue.put({'type': 'numclients', 'data': 0})
            server.queue.put({'type': 'clientnames', 'data':[]})
            server.close()
            for candidate in server.testingcandidates[:]:
                server.testingcandidates.remove(candidate)
                candidate.progress= 'untested'
                candidate.client= None
                server.waitingcandidates.insert(0, candidate)
            server.queue.put({'type': 'testingcandidates', 'data': server.testingcandidates, 'data2': len(server.candidates), 'data3': server.waitingcandidates})
            with open(os.getcwd()+'\\data\\serverdata.pickle', 'wb') as w:
                pickle.dump({'candidates':server.candidates,
                             'testingcandidates':server.testingcandidates,
                             'loadedfiles': server.loadedfiles,
                             'waiting': server.waitingcandidates}, w)
                                                
    if time.time()- waitstopper > 90:
        waitstopper= time.time()
        if serverOn:
            server.checkwait()
    if serverOn:
        server.Pump()
        if c==20: #every 0.2 seconds send an update about the testing candidates to the GUI
            server.queue.put({'type': 'testingcandidates', 'data': server.testingcandidates, 'data2': len(server.candidates), 'data3':server.waitingcandidates})
            if len(server.candidates)== 0:
                gui.status.config(text= 'Idle', fg= 'red')
            c= 0
        c+= 1
    time.sleep(0.01)
