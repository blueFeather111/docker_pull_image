This script was created when I encountered this problem due to my network:             
$ docker pull ubuntu:20.04         
Error response from daemon: Get "https://registry-1.docker.io/v2/": net/http: request canceled while waiting for connection (Client.Timeout exceeded while awaiting headers)       
            
By using this script you can download the docker image as tar file and load it locally.           
           
### usage         
python docker_pull_image.py ubuntu:20.04          
python docker_pull_image.py ubuntu:20.04 -o ubuntu_20_04.tar -a arm64      
python docker_pull_image.py hello-world:latest       



