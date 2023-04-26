# frankAllSkyCam
AllSkyCam software 
# FASE 1 - preparazione del sistema da SD card vuota
genera una SD con sistema operativo 64bit lite (no desktop)metti già in configurazione: SSH, localizzazione, wifi, username e passfare boot con login pi e pass scelta

configurazioni iniziali, dopo il primo bootaggiorna i pacchetti:sudo apt updatesudo apt upgrade

Riavvia:
sudo shutdown -r now
sudo raspi-config

1) Performance -> P2 - GPU Mem imposta a 256
2) Interface -> P5 - enable IC2 Bus  (serve per i relé)
=====tutte queste si impostano in fase di creazione SD. Se non fatte, allora:
2) System Options -> S1- Wireless LAN
3) System Options -> S5 - Boot autologin
4) System Options -> S3 - Password (metti la tua)
5) Localisation -> L1 - Tastiera generic 102 tasti, poi italiana, poi tasto "componi" = right Alt Gr
6) Localisation -> L2 - Timezone Italia
7) Localisation -> L4 - WLAN Country Italia
8) Interface - > P2 Enable SSH ===
assicurati di aver inserito bene le info sulla WiFi (ssid e password)

Riavvia:
sudo shutdown -r now

per sapere a quale wifi sei collegato:
iwgetid 

per sapere che IP hai
ifconfig

installa apache: 
sudo apt install apache2 -y

installa i pacchetti python:
sudo apt install python3-pip

installa le librerie usate 
pip3 install pytz
pip3 install suncalcPy


se hai i relé per gestire la fascia anticondensa ed il sensore di temperatura e umidità, bisogna installare anche questi 2:

sudo apt install python3-smbus
sudo apt-get install rpi.gpio  NON OCCORRE C'è GIA'

# SE VUOI FARE I TIMELAPSE:
sudo apt install ffmpeg


# FASE 3 NETWORK CONFIGURATION
E' necessario avere un IP statico sulla LAN
impostare IP statico editando il file:
nano /etc/dhcpcd.conf

aggiungere le 4 righe sotto. ovviamente, sostituire il proprio ip al 192.169.2.25 e l'indirizzo del proprio router al 192.168.2.1
interface eth0
static ip_address=192.168.2.25/24
static routers=192.168.2.1
static domain_name_servers=192.168.2.1 8.8.8.8

per la wifi, è possibile settare diverse configurazioni a seconda del SSID:
interface wlan0   static ip_address=192.168.1.60/24
   static routers=192.168.1.254
   static domain_name_servers=192.168.1.254 8.8.8.8

INSERIRE ISTRUZIONE PER LE WIFI MULTIPLE
Salva e chiudi il file.riavvia e vedi se ha preso IP giusto conifconfig
nota per sapere il ssid della rete in uso, digita:iwgetid 

fai un reboot:
sudo reboot -h now

FASE 3 INSTALLAZIONE FILE
Crea la cartella del programma (di default è sky ma la puoi cambiare):
mkdir /home/pi/logsmkdir /home/pi/imgsudo mkdir /var/www/html/img

# INSTALLAZIONE TRAMITE PYIP
pip3 install frank-AllSkyCamPi   
SOVRASCRIVERE TUTTI I FILE DELLA CARTELLA/home/pi/.local/lib/python3.9/site-packages/allskycam/CON QUELLI ALLEGATI A QUESTA MAIL 
CONFIGURAZIONE PARAMETRI:nano /home/pi/.local/lib/python3.9/site-packages/allskycam/config.txt

# INSTALLAZIONE SAMBA
sudo apt-get update
sudo apt-get upgrade
sudo apt-get install samba samba-common-bin
     
Se lo chiede, durante l'installazione, installare anche la parte DHCP.modifica la config. del file samba smb.conf:
sudo nano /etc/samba/smb.conf

aggiungere la seguente config alla fine

[pi]
path = /home/piread only = no
writeable = yes
create mask = 0777
directory mask = 0777
public = no
(salva ed esci)

abilita user pi a samba:
sudo smbpasswd -a pi
(inserisci la password di pi)

riavvia il servizio samba:
sudo systemctl restart smbd

DOPO aver installato samba, dal windows puoi aprire il disco del raspberry con 
\\192.168.2.25
inserisci le credenziali dell'utente pi ed avrai accesso alla cartella /home/pi

# FASE 4 COPIA DEI FILEcopia la pagina html:

sudo cp/home/pi/program/index.html /var/www/html/index.html


# FASE 5 CONFIGURAZIONE JOB CRONTAB  
python3 -m allskycam.crontab   
sudo reboot -h now

troverai i job in crontab:
crontab -l

0 1 * * * python3 -m allskycam.allskycamdelete >/dev/null 2>&1
0 8 * * * python3 -m allskycam.timelapse >/dev/null 2>&1
*/3 21-7 * * * sudo killall libcamera-still; python3 -m allskycam >/dev/null 2>&1
*/1 8-20 * * * sudo killall libcamera-still; python3 -m allskycam >/dev/null 2>&1
*/30 * * * * python3 -m allskycam.temp >/dev/null 2>&1*/5 * * * * python3 -m allskycam.watchDog >/dev/null 2>&1

la 1 è per cancellare i file piu' vecchi di 3gg
la 2 genera i timelapse e li carica via ftp al server indicato in config.txt
la 3 è per le foto ogni 3 minuti  tra le 21 e le 7 del mattino
la 4 è per le foto ogni minuto dalle 8 alle 20
la 5 è per la per la regolazione della temperatura (se non hai relé o sensori, non serve)
la 6 è il watchdog. Se non si genera un file negli ultimi 5 min, scrive il log e riavvia il gioco è fatto.

Se funziona:http://<ip del RaspBerry>vedi la pagina che si aggiorna ogni  minuto.l'immagine si aggiorna ogni 3 minuti di notte e ogni minuto di giorno
  
