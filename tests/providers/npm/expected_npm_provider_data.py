from __future__ import annotations


# Normalized expected outputs for tests/test_repos/npm.
# These values replaced the temporary RIG/SPADE bootstrap JSON.

EXPECTED_COMPONENT_IDS = {
    "component:npm:@monorepo/admin-portal",
    "component:npm:@monorepo/analytics",
    "component:npm:@monorepo/api-client",
    "component:npm:@monorepo/api-server",
    "component:npm:@monorepo/auth-lib",
    "component:npm:@monorepo/auth-service",
    "component:npm:@monorepo/build-aggregator",
    "component:npm:@monorepo/codegen",
    "component:npm:@monorepo/config",
    "component:npm:@monorepo/core",
    "component:npm:@monorepo/data-access",
    "component:npm:@monorepo/data-models",
    "component:npm:@monorepo/data-processor",
    "component:npm:@monorepo/logging-lib",
    "component:npm:@monorepo/metrics-lib",
    "component:npm:@monorepo/native-addon",
    "component:npm:@monorepo/notification",
    "component:npm:@monorepo/python-bridge",
    "component:npm:@monorepo/shared-ui",
    "component:npm:@monorepo/utils",
    "component:npm:@monorepo/wasm-module",
    "component:npm:@monorepo/web-app",
}

EXPECTED_AGGREGATOR_IDS = {
    "aggregator:npm:@monorepo/build-all",
    "aggregator:npm:@monorepo/deploy-all",
    "aggregator:npm:@monorepo/test-all",
}

EXPECTED_TEST_IDS = {
    "test:npm:@monorepo/admin-portal",
    "test:npm:@monorepo/analytics",
    "test:npm:@monorepo/api-client",
    "test:npm:@monorepo/api-server",
    "test:npm:@monorepo/auth-lib",
    "test:npm:@monorepo/auth-service",
    "test:npm:@monorepo/codegen",
    "test:npm:@monorepo/config",
    "test:npm:@monorepo/core",
    "test:npm:@monorepo/data-access",
    "test:npm:@monorepo/data-models",
    "test:npm:@monorepo/data-processor",
    "test:npm:@monorepo/logging-lib",
    "test:npm:@monorepo/metrics-lib",
    "test:npm:@monorepo/notification",
    "test:npm:@monorepo/shared-ui",
    "test:npm:@monorepo/test-all",
    "test:npm:@monorepo/utils",
    "test:npm:@monorepo/web-app",
}

EXPECTED_EXTERNAL_PACKAGE_IDS = {
    "external:npm:@types/bcrypt",
    "external:npm:@types/express",
    "external:npm:@types/jest",
    "external:npm:@types/jsonwebtoken",
    "external:npm:@types/node",
    "external:npm:@types/react",
    "external:npm:@types/react-dom",
    "external:npm:axios",
    "external:npm:bcrypt",
    "external:npm:express",
    "external:npm:fastify",
    "external:npm:jest",
    "external:npm:jsonwebtoken",
    "external:npm:mongoose",
    "external:npm:node-gyp",
    "external:npm:prom-client",
    "external:npm:react",
    "external:npm:react-dom",
    "external:npm:typescript",
    "external:npm:wasm-pack",
    "external:npm:webpack",
    "external:npm:winston",
}

EXPECTED_PACKAGE_MANAGER_IDS = (
    "pkgmgr:cargo",
    "pkgmgr:go",
    "pkgmgr:npm:root",
    "pkgmgr:python",
)

EXPECTED_REPRESENTATIVE_FILE_OWNERS = {
    "packages/core/src/index.ts": "component:npm:@monorepo/core",
    "packages/core/src/index.test.ts": "test:npm:@monorepo/core",
    "tools/codegen/main.py": "runner:npm:@monorepo/codegen:build",
    "package.json": "pkgmgr:npm:root",
    "tools/codegen/pyproject.toml": "pkgmgr:python",
    "modules/wasm-module/Cargo.toml": "pkgmgr:cargo",
    "modules/native-addon/go.mod": "pkgmgr:go",
}

EXPECTED_COMPONENT_LANGUAGES = {
    "component:npm:@monorepo/core": "typescript",
    "component:npm:@monorepo/native-addon": "go",
    "component:npm:@monorepo/python-bridge": "python",
    "component:npm:@monorepo/wasm-module": "typescript",
    "component:npm:@monorepo/web-app": "typescript",
}

EXPECTED_COMPONENT_KINDS = {
    "component:npm:@monorepo/auth-service": "service",
    "component:npm:@monorepo/build-aggregator": "package",
    "component:npm:@monorepo/core": "package",
    "component:npm:@monorepo/shared-ui": "library",
    "component:npm:@monorepo/web-app": "binary",
}
