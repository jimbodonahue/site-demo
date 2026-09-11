#!/bin/bash

# Function to deploy a cloud function
deploy_function() {
    local function_name=$1
    local function_dir=$2
    local generation=$3
    local cron_syntax=${4:-""}
    local message_bodies=${5:-""}
    
    # Copy the common folder and requirements.txt to the function directory
    cp -r scripts/common $function_dir/
    cp scripts/requirements.txt $function_dir/

    # Deploying as a Cloud Function (Gen1)
    echo "Deploying $function_name as Cloud Function $generation..."

    # Conditionally set Docker registry option if deploying to Gen1
    docker_registry_option=""
    if [ "$generation" = "no-gen2" ]; then
        docker_registry_option="--docker-registry=artifact-registry"
    fi

    # Set timeout based on generation
    timeout_value="540s"
    if [ "$generation" = "gen2" ]; then
        timeout_value="3600s"
    fi

    # Formulate generation option
    generation_option=""
    if [ "$generation" = "gen2" ]; then
        generation_option="--gen2"
    fi

    # Execute the gcloud command and capture output
    gcloud functions deploy "$function_name" \
        --region=us-central1 \
        --source="$function_dir" \
        --runtime python311 --trigger-http --allow-unauthenticated \
        --set-env-vars DB_HOST="${DB_HOST}",DB_PWD="${DB_PWD}",DB_USER="${DB_USER}",DB_NAME="${DB_NAME}" \
        --entry-point=main \
        --timeout="$timeout_value" \
        --memory=4GiB \
        --cpu=2 \
        --concurrency=5 \
        --min-instances=0 \
        --max-instances=50 \
        $generation_option \
        $docker_registry_option || { echo "Failed to deploy $function_name"; exit 1; }

    # Create Cloud Scheduler jobs for each message body (if provided)
    if [[ -n "$cron_syntax" && -n "$message_bodies" ]]; then
        local job_name_prefix="${function_name}-job-"
        
        # Convert message bodies into an array, splitting on '|'
        IFS='|' read -r -a message_array <<< "$message_bodies"

        for job_count in "${!message_array[@]}"; do 
            message_body="${message_array[$job_count]}"
            job_name="${job_name_prefix}${job_count}"
            echo "Creating Cloud Scheduler job $job_name for $function_name with message body: $message_body..."

            gcloud scheduler jobs create http $job_name \
                --schedule="$cron_syntax" \
                --time-zone="America/New_York" \
                --uri="https://us-central1-${PROJECT_ID}.cloudfunctions.net/$function_name" \
                --http-method="POST" \
                --headers="Content-Type=application/json" \
                --message-body="$message_body" \
                --location="us-central1" \
                --oidc-service-account-email="${SERVICE_ACCOUNT_EMAIL}" \
                --oidc-token-audience="https://us-central1-${PROJECT_ID}.cloudfunctions.net/$function_name" \
                --quiet \
                --attempt-deadline=30m

        done
    else
        echo "Skipping Cloud Scheduler job creation for $function_name (no cron syntax or message bodies provided)."
    fi

    # Clean up: remove the common folder and requirements.txt from the function directory
    rm -rf $function_dir/common
    rm -f $function_dir/requirements.txt
}

if git diff --name-only $GITHUB_BEFORE $GITHUB_SHA | grep -q 'scripts/<folder_name>/'; then
    # Set this margin for 15 minutes
    deploy_function "<function_name>_function" "scripts/<folder_name>" "no-gen2" "0 0 * * 7" '{"hello": "world"}'
fi