def call(String branch) {
    if (branch != 'release') {
        error "deploy runs only from release, not ${branch}"
    }
    sh './scripts/deploy.sh'
}
