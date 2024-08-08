# spi-api-gw

Serverless Application Model for Single Page Importer notes.


## Python Virtual Environment
Code for this project is built using a Python virtual environment. Briefly, to initialize the environment you should be in the project directory and then do:

	python -m venv .

then to use the environment from your shell (e.g. bash or zsh)

	. bin/activate

If you need to move to a different Python project, deactivate your environment:

	deactivate

## Installing SAM
This project is built using AWS Serverless Application Model software. You will need SAM installed in order build an install this application. See the documentation [here](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) for installation instructions.

## Prerequisites
Developer testing and debugging requires that the developer have an AWS account that is  not shared with any other developers running this project. To build and test in a personal environment:
	Obtain an AWS Security Key (https://us-east-1.console.aws.amazon.com/iam/home#/security_credentials)
	Copy the Key ID and Secret into your AWS credentials file (~/.aws/credentials) as follows:
		[default]
		aws_access_key_id = <key id goes here>
		aws_secret_access_key = <secret key goes here>


You should be able to build the application directly after checkout (assuming that you have SAM, AWS-CLI installed and an AWS account).

##Building
The application is built with `sam`. The configuration for the build is held in the files `samconfig.yaml` and `template.yaml`. The first file contains the values that change from one environment to another. The sections `local`, `dev`, `preprod`, and `prod` contain the overrides for each of the environments. The sections `dev`, `preprod` and `prod` contain the parameters for the three different VAEC envrionments the application will run in. `local` is for developer deployment.

### Commands for Building
Before building and deploying the application, the required infrastructure must exist on the target AWS account. The infrastructure consists of the durable AWS resources, such as SNS topics and S3 buckets, which are not added, removed or modified when the application is deployed. The infrastructure resources are defined in the `infrastructure` directory. To create the infrastructure resources:
1. Navigate to the `infrastructure` directory
2. Optionally, modify the samconfig.yaml file as follows:
	1. Copy and paste the entire 'local' section
	2. Rename from 'local' to a unique identifier for the target account and region, the standard has been to use developer initials for a developer build and test environment
	3. Change the 'subnets' within the local/deploy/parameter_overrides, the values must be two subnets from different availability zones within the target account and region
	4. Note that the 'environment' should remain as 'local'
3. Run the following command:
	sam build --config-file samconfig.yaml --config-env <unique identifier  from step 2>
The infrastructure resources only need to be created once per environment.

To build the application, navigate to the root directory and run the following comman

	sam build --config-file samconfig.yaml
	
If the build is successful you will see this output:

	Building codeuri: /Users/chaz/Projects/cies/spi_api_gw/src runtime: python3.11 metadata: {} architecture: x86_64 functions: GetStatusFunction, GetTextFunction, SNSFunction, SubmitTextFunction, OCRStatusNotificationDefaultRouteFunction, OCRStatusNotificationFunction                           
 	Running PythonPipBuilder:ResolveDependencies                                                                                                                                                                                                                                                       
 	Running PythonPipBuilder:CopySource                                                                                                                                                                                                                                                                

	Build Succeeded

	Built Artifacts  : .aws-sam/build
	Built Template   : .aws-sam/build/template.yaml

	Commands you can use next
	=========================
	[*] Validate SAM template: sam validate
	[*] Invoke Function: sam local invoke
	[*] Test Function in the Cloud: sam sync --stack-name {{stack-name}} --watch
	[*] Deploy: sam deploy --guided`

At this point, it is suggested that you validate the `template.yaml` file. To do that run:

	sam validate --lint --config-file samconfig.yaml
	
If there are any schema violations, they will be listed, otherwise you will see a message similar to:

	/Users/chaz/Projects/cies/spi_api_gw/template.yaml is a valid SAM Template
	
To deploy the application, execute the following command, changing the `config-env` value to match the environment you are deploying to:

	sam deploy --config-env ceb --config-file samconfig.yaml
	
If the template is correct, and there are no errors, you will be prompted to confirm the deployment:

	Previewing CloudFormation changeset before deployment
	======================================================
	Deploy this changeset? [y/N]: y


To list the endpoints that were created during deployment, execute the following (change the stack name as appropriate):

	sam list endpoints --stack-name spi-ocr-app-local --config-file samconfig.yaml --output json
	
This will output a listing similar to this:

	[
	  {
	    "LogicalResourceId": "GetStatusFunction",
	    "PhysicalResourceId": "project-OCR-GetStatusFunction-local",
	    "CloudEndpoint": "-",
	    "Methods": "-"
	  },
	  {
	    "LogicalResourceId": "GetTextFunction",
	    "PhysicalResourceId": "project-OCR-GetTextFunction-local",
	    "CloudEndpoint": "-",
	    "Methods": "-"
	  },
	  {
	    "LogicalResourceId": "OCRStatusNotificationAPI",
	    "PhysicalResourceId": "2ssi1nm41e",
	    "CloudEndpoint": [
	      "https://2ssi1nm41e.execute-api.us-east-2.amazonaws.com/local"
	    ],
	    "Methods": []
	  },
	  {
	    "LogicalResourceId": "OCRStatusNotificationDefaultRouteFunction",
	    "PhysicalResourceId": "project-ocr-status-subscription-function-local",
	    "CloudEndpoint": "-",
	    "Methods": "-"
	  },
	  {
	    "LogicalResourceId": "OCRStatusNotificationFunction",
	    "PhysicalResourceId": "project-ocr-notification-function-local",
	    "CloudEndpoint": "-",
	    "Methods": "-"
	  },
	  {
	    "LogicalResourceId": "SNSFunction",
	    "PhysicalResourceId": "project-OCR-SNSFunction-local",
	    "CloudEndpoint": "-",
	    "Methods": "-"
	  },
	  {
	    "LogicalResourceId": "ServerlessRestApi",
	    "PhysicalResourceId": "viukt81kl6",
	    "CloudEndpoint": [
	      "https://viukt81kl6.execute-api.us-east-2.amazonaws.com/Prod",
	      "https://viukt81kl6.execute-api.us-east-2.amazonaws.com/Stage"
	    ],
	    "Methods": [
	      "/ocr['post', 'options']",
	      "/get_text['options', 'get']",
	      "/get_status['options', 'get']"
	    ]
	  },
	  {
	    "LogicalResourceId": "SpiHttpApiGateway",
	    "PhysicalResourceId": "wpzx2hglya",
	    "CloudEndpoint": [],
	    "Methods": []
	  },
	  {
	    "LogicalResourceId": "SubmitTextFunction",
	    "PhysicalResourceId": "project-OCR-SubmitTextFunction-local",
	    "CloudEndpoint": "-",
	    "Methods": "-"
	  }
	]
	
Make note of the `https` endpoints, you will need those for calling the REST portion of the application.

At this point the application should be running.

## Calling REST Functions
Once the application has been built and installed, it can be tested with the `test1.py` application. The easiest way to run the test is to edit and call the shell script `run_test.sh`. You will need to provide a sample PDF file (for OCR'ing), the URL of the installed application and an access key.

The application provides 3 REST functions:

	/functions/document/handler.py
	/functions/text/handler.py
	/functions/notification/handler.py

To test you can use the `test1.py` file located in `tests`. A shell script `run_test.sh` is setup to cal l the program. Edit the shell script and change the URL to the endpoint obtained from the `sam list` command. Execute the shell script and you should see output similar to:

	response: <Response [200]>
	jobId: {'JobId': 'f7dc795303f4a6fa9ba490b9d81afa69e8a885d09bac53752e2275b252bfe608'}
	response jobid: f7dc795303f4a6fa9ba490b9d81afa69e8a885d09bac53752e2275b252bfe608
	get_response: b'{"status":"SUBMITTED"}' 
	
When the job is complete, the text extracted from Textract will be printed to the screen. 

There are two sample PDF file included in the `samples` directory. One is a one page report the other is a three page report.

### /functions/document/handler.py
This function is used to write a file to the input S3 bucket, get the status of the OCR on the file, and (re)retreive the original document. Along with the file, the following HTTP Header values should be set:

	'Content-Type': 'application/octet-stream',
    'x-amz-date': amz_date,
    'Filename' : filename,
    'Siteid': 'site-r',
    'Userid' : 'fred user'
    
The base portion of the filename should be a UUID (version 4), e.g. `276b91cd-5d78-4feb-bc94-9d1129b851cd.pdf`. The file must be converted to bas64 encoding and submitted as a JSON object:

	{'body': 'JVBERi0xLjQKJeLjz9MNCjEgMCBvYmoKPDwgCi9D......'}

When the file is submitted to the REST function, it will be saved in an S3 bucket where it can be retrieved by Textract for analysis. The function will return a Job Id as JSON when the file has been submitted to Textract.

	{'JobId': '323ffcee86e112be01287607d665c0a66d45902386eac4aad0a578fde9dd8a7c'}
	
In order to monitor the state of the submitted job, the function `get_status` can be called with the JobId, e.g.

	(aws-url)/get_status?jobId={jobIdJson['JobId']
	
	
The `get_status` function will query for the current status of the job and return one of a possible three values:

	SUCCEEDED
	ERROR
	FAILED

It can take a few seconds to several minutes to process a document. When the status `SUCCEEDED` has been returned, the `get_text` function can be called with the JobId to retrieve the OCR'd text.

	(aws-url)/get_text?jobId={jobIdJson['JobId']
	
The response will be similar to this snippet, a simple JSON object with each line of text separated by one or more newline codes `\n`:

		{"parsedText":"Patient: DOE, JOHN\nMRN JD4USARAD\n\nExam Date:\n05/25/2010\n\nReferring Physician: DR. DAVID LIVESEY\n\nDOB:\..."}


    
##SAM Notes (from running `sam init`)
Congratulations, you have just created a Serverless "Hello World" application using the AWS Serverless Application Model (AWS SAM) for the `python3.12` runtime, and options to bootstrap it with [**AWS Lambda Powertools for Python**](https://awslabs.github.io/aws-lambda-powertools-python/latest/) (Lambda Powertools) utilities for Logging, Tracing and Metrics.

Powertools is a developer toolkit to implement Serverless best practices and increase developer velocity.

## Powertools features

Powertools provides three core utilities:

- **[Tracing](https://awslabs.github.io/aws-lambda-powertools-python/latest/core/tracer/)** - Decorators and utilities to trace Lambda function handlers, and both synchronous and asynchronous functions
- **[Logging](https://awslabs.github.io/aws-lambda-powertools-python/latest/core/logger/)** - Structured logging made easier, and decorator to enrich structured logging with key Lambda context details
- **[Metrics](https://awslabs.github.io/aws-lambda-powertools-python/latest/core/metrics/)** - Custom Metrics created asynchronously via CloudWatch Embedded Metric Format (EMF)

Find the complete project's [documentation here](https://awslabs.github.io/aws-lambda-powertools-python).

### Installing AWS Lambda Powertools for Python

With [pip](https://pip.pypa.io/en/latest/index.html) installed, run:

```bash
pip install aws-lambda-powertools
```

### Powertools Examples

- [Tutorial](https://awslabs.github.io/aws-lambda-powertools-python/latest/tutorial)
- [Serverless Shopping cart](https://github.com/aws-samples/aws-serverless-shopping-cart)
- [Serverless Airline](https://github.com/aws-samples/aws-serverless-airline-booking)
- [Serverless E-commerce platform](https://github.com/aws-samples/aws-serverless-ecommerce-platform)
- [Serverless GraphQL Nanny Booking Api](https://github.com/trey-rosius/babysitter_api)

## Working with this project

This project contains source code and supporting files for a serverless application that you can deploy with the SAM CLI. It includes the following files and folders.

- hello_world - Code for the application's Lambda function.
- events - Invocation events that you can use to invoke the function.
- tests - Unit tests for the application code.
- template.yaml - A template that defines the application's AWS resources.

The application uses several AWS resources, including Lambda functions and an API Gateway API. These resources are defined in the `template.yaml` file in this project. You can update the template to add AWS resources through the same deployment process that updates your application code.

If you prefer to use an integrated development environment (IDE) to build and test your application, you can use the AWS Toolkit.
The AWS Toolkit is an open source plug-in for popular IDEs that uses the SAM CLI to build and deploy serverless applications on AWS. The AWS Toolkit also adds a simplified step-through debugging experience for Lambda function code. See the following links to get started.

- [CLion](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [GoLand](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [IntelliJ](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [WebStorm](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [Rider](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [PhpStorm](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [PyCharm](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [RubyMine](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [DataGrip](https://docs.aws.amazon.com/toolkit-for-jetbrains/latest/userguide/welcome.html)
- [VS Code](https://docs.aws.amazon.com/toolkit-for-vscode/latest/userguide/welcome.html)
- [Visual Studio](https://docs.aws.amazon.com/toolkit-for-visual-studio/latest/user-guide/welcome.html)

### Deploy the sample application

The Serverless Application Model Command Line Interface (SAM CLI) is an extension of the AWS CLI that adds functionality for building and testing Lambda applications. It uses Docker to run your functions in an Amazon Linux environment that matches Lambda. It can also emulate your application's build environment and API.

To use the SAM CLI, you need the following tools.

- SAM CLI - [Install the SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
- [Python 3 installed](https://www.python.org/downloads/)
- Docker - [Install Docker community edition](https://hub.docker.com/search/?type=edition&offering=community)

To build and deploy your application for the first time, run the following in your shell:

```bash
sam build --use-container
sam deploy --guided
```

The first command will build the source of your application. The second command will package and deploy your application to AWS, with a series of prompts:

- **Stack Name**: The name of the stack to deploy to CloudFormation. This should be unique to your account and region, and a good starting point would be something matching your project name.
- **AWS Region**: The AWS region you want to deploy your app to.
- **Confirm changes before deploy**: If set to yes, any change sets will be shown to you before execution for manual review. If set to no, the AWS SAM CLI will automatically deploy application changes.
- **Allow SAM CLI IAM role creation**: Many AWS SAM templates, including this example, create AWS IAM roles required for the AWS Lambda function(s) included to access AWS services. By default, these are scoped down to minimum required permissions. To deploy an AWS CloudFormation stack which creates or modifies IAM roles, the `CAPABILITY_IAM` value for `capabilities` must be provided. If permission isn't provided through this prompt, to deploy this example you must explicitly pass `--capabilities CAPABILITY_IAM` to the `sam deploy` command.
- **Save arguments to samconfig.toml**: If set to yes, your choices will be saved to a configuration file inside the project, so that in the future you can just re-run `sam deploy` without parameters to deploy changes to your application.

You can find your API Gateway Endpoint URL in the output values displayed after deployment.

### Use the SAM CLI to build and test locally

Build your application with the `sam build --use-container` command.

```bash
spi_api_gw$ sam build --use-container
```

The SAM CLI installs dependencies defined in `hello_world/requirements.txt`, creates a deployment package, and saves it in the `.aws-sam/build` folder.

Test a single function by invoking it directly with a test event. An event is a JSON document that represents the input that the function receives from the event source. Test events are included in the `events` folder in this project.

Run functions locally and invoke them with the `sam local invoke` command.

```bash
spi_api_gw$ sam local invoke HelloWorldFunction --event events/event.json
```

The SAM CLI can also emulate your application's API. Use the `sam local start-api` to run the API locally on port 3000.

```bash
spi_api_gw$ sam local start-api
spi_api_gw$ curl http://localhost:3000/
```

The SAM CLI reads the application template to determine the API's routes and the functions that they invoke. The `Events` property on each function's definition includes the route and method for each path.

```yaml
Events:
  HelloWorld:
    Type: Api
    Properties:
      Path: /hello
      Method: get
```

### Add a resource to your application

The application template uses AWS Serverless Application Model (AWS SAM) to define application resources. AWS SAM is an extension of AWS CloudFormation with a simpler syntax for configuring common serverless application resources such as functions, triggers, and APIs. For resources not included in [the SAM specification](https://github.com/awslabs/serverless-application-model/blob/master/versions/2016-10-31.md), you can use standard [AWS CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html) resource types.

### Fetch, tail, and filter Lambda function logs

To simplify troubleshooting, SAM CLI has a command called `sam logs`. `sam logs` lets you fetch logs generated by your deployed Lambda function from the command line. In addition to printing the logs on the terminal, this command has several nifty features to help you quickly find the bug.

`NOTE`: This command works for all AWS Lambda functions; not just the ones you deploy using SAM.

```bash
spi_api_gw$ sam logs -n HelloWorldFunction --stack-name spi_api_gw --tail
```

You can find more information and examples about filtering Lambda function logs in the [SAM CLI Documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-logging.html).

### Tests

Tests are defined in the `tests` folder in this project. Use PIP to install the test dependencies and run tests.

```bash
spi_api_gw$ pip install -r tests/requirements.txt --user
# unit test
spi_api_gw$ python -m pytest tests/unit -v
# integration test, requiring deploying the stack first.
# Create the env variable AWS_SAM_STACK_NAME with the name of the stack we are testing
spi_api_gw$ AWS_SAM_STACK_NAME="spi_api_gw" python -m pytest tests/integration -v
```

### Cleanup

To delete the sample application that you created, use the AWS CLI. Assuming you used your project name for the stack name, you can run the following:

```bash
sam delete --stack-name "spi_api_gw"
```

## Resources

See the [AWS SAM developer guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html) for an introduction to SAM specification, the SAM CLI, and serverless application concepts.

Next, you can use AWS Serverless Application Repository to deploy ready to use Apps that go beyond hello world samples and learn how authors developed their applications: [AWS Serverless Application Repository main page](https://aws.amazon.com/serverless/serverlessrepo/)
