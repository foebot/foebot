const merge = require('merge');

let config = {
    anyproxy: {
        port: 8080,
        webInterface: {
            enable: true,
            webPort: 8081
        },
        interceptPatten: 'forgeofempires.com/'
    },
    socketio: {
        port: 8090
    }
};

config.browser.proxy = 'http://0.0.0.0:'+config.anyproxy.port;

module.exports = {
    val: function(property) {
        return config[property];
    },
    all: function() {
        return config;
    },
    configure: function(configObject) {
        config = merge(config, configObject);
    }
};