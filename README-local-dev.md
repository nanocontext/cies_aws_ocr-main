# Local Dev Setup Notes
- install `aws sam`
- install `docker`
	- create docker network
	
		`docker network create -d bridge sam-testing-net`
	- install dynamodb locally

		`docker run --network sam-testing-net -p 8000:8000 --name dynamo-local amazon/dynamodb-local`
- do the usual `sam init` and coding stuff

- note that your local endpoint for `dynamodb` will be `dynamo-local`, this is available thru the `docker dns`
	
- build api

	`sam build --docker-network sam-testing-net `
	
- run it

	`sam local start-api --docker-network sam-testing-net`

		