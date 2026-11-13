class DeployTest extends BasePipelineTest {
    void testOtherBranchStops() {
        shouldFail { loadScript('vars/deploy.groovy').call('main') }
    }
}
