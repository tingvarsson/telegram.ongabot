pipeline {
  agent any
  stages {
    stage('Redeploy') {
      steps {
        sh 'curl 10.0.0.2:9000/hooks/redeploy-ongabot'
      }
    }
  }
}
