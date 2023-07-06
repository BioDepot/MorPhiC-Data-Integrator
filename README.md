# Covid Dashboard
Welcome to the Bwb dashboard

## Getting Started
### Prequisites
Have python and Virtual Environments installed. Here is the python version I am using:

    ```shell
    $ python3 --version
    Python 3.10.6
    ```

### Set up
In the project root directory:
- Create a virtual environment with python >=3.7
- Install Dependencies: 
  - With PIP: 
  ```shell 
  pip install -r requirement.txt
  ```
  - With Anaconda: 
  ```shell
  conda install --file requirements.txt
  ```

- Install Docker
  - Follow the installation proces [here](https://github.com/BioDepot/BioDepot-workflow-builder#installing-and-starting-docker)
  - I installed for Linux

### Start the project
1. Start Bwb
    - Follow the Starting Bwb process [here](https://github.com/BioDepot/BioDepot-workflow-builder#starting-bwb) 
    - I am running Bwb on Linux, the following may be different on your setup
    ```shell
    $ sudo docker run --rm -p 6080:6080 -v ${PWD}:/data -v /var/run/docker.sock:/var/run/docker.sock -v /tmp/.X11-unix:/tmp/.X11-unix  --privileged --group-add root biodepot/bwb
    ```

2. Run the web app with
    ```shell
    $ python run.py
    ```
    or 
    ```shell
    $ flask run
    ```
