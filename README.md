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
  - Follow the installation process [here](https://github.com/BioDepot/BioDepot-workflow-builder#installing-and-starting-docker)
  - Note:
    - I installed for Linux
    - I setup Docker with the option of executing the docker command without Sudo

### Start the project
1. Activate your python virtual environment

2. Run the web app with
    ```shell
    $ python run.py
    ```
    or 
    ```shell
    $ flask run
    ```
