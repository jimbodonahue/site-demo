
# Stock Screener

Describe your project here. A brief description of what the project does and who it's for.

## Prerequisites

Before you begin, ensure you have met the following requirements:

-   You have installed the latest version of Python.
-   You have a Windows/Linux/Mac machine.
-   You have read `cloud_sql_proxy` documentation (if applicable).

## Setting Up the Project

To set up the project, follow these steps:

1.  **Clone the Repository:**
    
    `git clone [URL to your repository]
    cd [repository name]` 
    
2.  **Set Up Virtual Environment:**
    
    -   If you don't have a virtual environment yet:
        
        `python -m venv venv` 
        
    -   Activate the virtual environment:
        
        -   On Windows:
            
            `.\venv\Scripts\activate` 
            
        -   On Linux/Mac:
            
            `source venv/bin/activate` 
            
3.  **Install Dependencies:**
    
    `pip install -r requirements.txt` 
    
4.  **Set Up Cloud SQL Proxy (Optional):**
    
    -   Download `cloud_sql_proxy.exe` for Windows or appropriate binary for other OS.
        
    -   Run Cloud SQL Proxy:
        
        `.\cloud_sql_proxy.exe -instances=<cloud-sql-instance-connection-name>=tcp:127.0.0.1:5432` 
        
        Ensure the instance connection name matches your Cloud SQL instance.
        

## Running the Project

To run the project, execute the following command:

### Activate the Virtual Environment

First, activate your virtual environment (venv). The activation command varies depending on your shell.

### Set PYTHONPATH on Windows

Run the following command in your shell to set the `PYTHONPATH`:

```powershell
$env:PYTHONPATH='Your/Project/Directory/Path'
```

Replace Your/Project/Directory/Path with the actual path to your project directory. This allows you to import modules like common.utils in your Python code.

If you are in your project root directory, then you can run this command to set the `PYTHONPATH`:

```powershell
$env:PYTHONPATH='./'
```