# Contribution Guidelines

In order to contribute changes to this repo, refer to the following steps.

## Table of Contents
- [Contribution Guidelines](#contribution-guidelines)
  - [Table of Contents](#table-of-contents)
  - [Getting Started](#getting-started)
    - [Prerequisites](#prerequisites)
    - [Fork and Clone the Repository](#fork-and-clone-the-repository)
  - [Create a feature branch](#create-a-feature-branch)
  - [Test cases](#test-cases)
  - [Merge/Pull request](#mergepull-request)
  - [Releases](#releases)
  - [Issues](#issues)

## Getting Started

### Prerequisites
Before starting, ensure you have the following installed:

- Python (>=3.11)

### Fork and Clone the Repository
- Clone the repository from GitHub:
   ```bash
   git clone https://github.com/Respiree/backend_data_processing.git
   cd dataprocessing
   ```


## Create a feature branch

- Pull from the `main` branch into your local drive. From there, create a feature branch with a descriptive name on what the new feature is meant to do. For example:

`git checkout -b feature/add_sensor_test_case`

- Make your changes on the feature branch. Note to never make changes on the `main` branch directly.


## Test cases

- For the functionality to be included, write some test cases for it.

- Run the testing framework to ensure that there are no breaking changes to the existing code. The test cases must all pass for the merge request to be accepted.

- Refer to the section in `README.md`, under the section `Running the test cases` for a automated way to execute them.

- N.B: The checking of test cases will be automated in the future with a CI/CD framework (e.g. Jenkins)


## Merge/Pull request

- Once the feature branch is complete and ready to be merged into the `main` branch, submit a pull request on github (to merge the feature branch into the `main` branch) and assign another team member to review the code.

- Once the review is done and all issues resolved, the reviewer will merge it into `main` branch. It is good practice to squash the commits during the merge, and also to delete the feature branch after the merge is successful.


## Releases

- When it is time for a publish a release, release the `main` branch with the updated version number.

## Issues

- If any bugs are spotted in this code base, submit an issue on github describing the problem and steps required to reproduce it. Be as descriptive as possible.
 