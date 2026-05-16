# Data Processing Backend
The data processing backend service is designed to handle and transform raw vital signal data, making it readily accessible for clients.


## Table of Contents
- [Data Processing Backend](#data-processing-backend)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Running application](#running-application)
  - [Data backup](#data-backup)
  - [Testing](#testing)
  - [Testing with Coverage](#testing-with-coverage)
  - [Django Admin Portal](#django-admin-portal)
  - [API Document](#api-document)
  - [License Scanning](#license-scanning)
    - [How It Works](#how-it-works)
    - [How to Run the Workflow](#how-to-run-the-workflow)
      - [To trigger the workflow manually:](#to-trigger-the-workflow-manually)
    - [Example Output](#example-output)
      - [CSV Output (license\_report.csv)](#csv-output-license_reportcsv)
      - [Markdown Output (pip-licenses --format=markdown)](#markdown-output-pip-licenses---formatmarkdown)


## Prerequisites 
Before starting, ensure you have the following installed:
- Install Python 3.11
- Install Redis
- Install Postgres SQL database
- Create virtual environment in the root directory of the project and activate it
- Install the dependencies using the command below
```bash
pip install -r requirements.txt
```
- Create `.env` file inside the `dataprocessing` directory (inside folder where manage.py located). Sample of the content can be found in `./dataprocessing/sample.env`
- Under `dataprocessing/dataprocessing/` folder, create a `secrets.py` file, which includes the following:
```
auth_login = {
    'username': '<username>',
    'password': '<password>'
}
```
The credentials will serve as the authentication for running the API calls. Remember to not commit this file into the repository. 

## Running application

- If there is any update in the database model, run the command below
```bash
python manage.py makemigrations
python manage.py migrate
```

- Create superuser
```bash
python manage.py createsuperuser
```

- Celery worker
```bash
celery -A dataprocessing worker --loglevel=info
```

- Celery beat
```bash
celery -A dataprocessing beat --loglevel=info
```

- Celery flower
```bash
celery -A dataprocessing flower --persistent=True --db="flower" --basic_auth=system:manager
```

- Collect static files
```bash
python manage.py collectstatic
```


- Navigate to `./dataprocessing` and run the command below
```bash
python manage.py runserver 0.0.0.0:9000
```

## Data backup

- Run the command below and it will take a dump
```bash
python manage.py dynamo_db_migrate
``` 

## Testing
- Download test dataset under `./dataprocessing/data_app/tests`
```bash
aws s3 cp s3://respiree-datasets/dp_onprime_test_data/test_data_onprime_1.zip .
```

- Run the test cases using the command below
```bash
cd dataprocessing/
python manage.py test
```

## Testing with Coverage
To include test coverage in the project, follow the steps:
- Run tests with coverage. Use the following command:
```bash
coverage run manage.py test
```
- Generate coverage report. For a summary in the terminal:
```bash
coverage report --fail-under=90
```
For an HTML report:
```bash
coverage html
# Open htmlcov/index.html in your browser
```

## Django Admin Portal
The portal can be accessed via the URL below
```
{{URL}}:8000/admin/
```

## API Document
After deploying applicatgion, the API document can be viewed in Swagger
- Swagger
```
{{URL}}:6887/swagger/
```

## License Scanning

### How It Works

The License Scanning workflow scans all installed Python packages and generates a report that includes package names, version, license types, and authors. The report is automatically uploaded as an artifact in GitHub Actions.

### How to Run the Workflow

The workflow runs automatically on:

- Every push to the main branch
- Every pull request targeting the main branch
- Manually via workflow dispatch

#### To trigger the workflow manually:

1. Go to the Actions tab in your GitHub repository.
2. Select License and Package Information from the workflow list.
3. Click Run workflow and choose the branch.

### Example Output

#### CSV Output (license_report.csv)

| Name              | Version | License                   | Author                  |
| ----------------- | ------- | ------------------------- | ----------------------- |
| `python-dotenv`   | 0.19.2  | BSD License               | Saurabh Kumar           |
| `requests`        | 2.32.2  | Apache Software License   | Kenneth Reitz           |
| `requests-mock`   | 1.12.1  | Apache Software License   | Jamie Lennox            |
| `starlette`       | 0.37.2  | BSD License               | Tom Christie            |

#### Markdown Output (pip-licenses --format=markdown)

```bash
 Name                Version     License                               Author
 python-dotenv       0.19.2      BSD License                           Saurabh Kumar                                                                                                       
 requests            2.32.2      Apache Software License               Kenneth Reitz                                                                                                        
 requests-mock       1.12.1      Apache Software License               Jamie Lennox 
 starlette           0.37.2      BSD License                           Tom Christie
```
After execution, the license report is available as an artifact in GitHub Actions under Summary > Artifacts > license-report.
