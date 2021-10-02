
const merge = require('merge');
const AnyProxy = require('anyproxy');
const server = require('http').createServer();
const io = require('socket.io')(server);
const request = require('request');
const shell = require('shelljs');

const config = {
    anyproxy: {
        port: 8080,
        webInterface: {
            enable: false,
            webPort: 8081
        }
    },
    intercept: {
        regex: 'forgeofempires',
        method: 'POST',
        pathStartsWith: '/game/json',
        content: 'json',
        requestClass: 'QuestService'
    },
    socketio: {
        port: 8090
    }
};

shell.mkdir('-p', '/tmp/anyproxy/cache');

/* CREATE A FORWARD CLASS */
const Forward = function() {
    this.summary = 'Forward';
    this.regex = new RegExp(config.intercept.regex);
};
// return True if anyproxy should intercept request and  response
Forward.prototype.beforeDealHttpsRequest = function*(req) {
    const found = this.regex.test(req.host);
    return found;
};
// intercept before send request to server
Forward.prototype.beforeSendRequest = function*(req) {
    return null
};
// deal response before send to client
Forward.prototype.beforeSendResponse = function*(req, res) {
    if (req.requestOptions.method === config.intercept.method &&
        req.requestOptions.path.startsWith(config.intercept.pathStartsWith) &&
        res.response.header['Content-Type'].includes(config.intercept.content)) {
        let jsonBody = JSON.parse(res.response.body.toString());
        if(Array.isArray(jsonBody)) {
            jsonBody.forEach(el => {
                if(el.requestClass === config.intercept.requestClass) {
                    // console.log('Emit quests: '+JSON.stringify(el));
                    console.log('[AnyProxy] Forwarding quest data to http://0.0.0.0:'+config.socketio.port);
                    request.post('http://0.0.0.0:'+config.socketio.port, { json: el }, (err, res, body) => {
                        if (err) { console.log(err); }
                        else { console.log('[AnyProxy] Quest data forwarded.'); }
                    });
                    // io.emit('rq', el);
                }
            });
        }
    }
    return null;
};
const forward = new Forward();

/* CREATE AN ANYPROXY */
// generate a CA certificate
const exec = require('child_process').exec;
if (!AnyProxy.utils.certMgr.ifRootCAFileExists()) {
    AnyProxy.utils.certMgr.generateRootCA((error, keyPath) => {
        // let users to trust this CA before using proxy
        if (!error) {
            const certDir = require('path').dirname(keyPath);
            console.log('[AnyProxy] The cert is generated at', certDir);
        } else {
            console.error('error when generating rootCA', error);
        }
    });
}

const options = merge({
    rule: forward,
    throttle: 10000,
    forceProxyHttps: false,
    wsIntercept: true,
    silent: true,
    dangerouslyIgnoreUnauthorized: true
}, config.anyproxy);
const proxyServer = new AnyProxy.ProxyServer(options);

proxyServer.on('ready', () => {
    console.info('[AnyProxy] AnyProxy ready and listening on '+config.anyproxy.port+'.');
    if (config.anyproxy.webInterface.enable)
        console.info('[AnyProxy] AnyProxy webInterface is available on http://0.0.0.0:'
            +config.anyproxy.webInterface.webPort);
});
let stop = false;
proxyServer.on('error', (e) => {
    console.log('[AnyProxy] Error caught.');
    console.error(e);
    proxyServer.close(() => {
        if(!stop) {
          console.log('[AnyProxy] Restarting AnyProxy.');
          proxyServer.start();
        }
    });
});
proxyServer.start();

//when finished
const close =  async function() {
    stop = true;
    console.log('[AnyProxy] Closing AnyProxy.');
    proxyServer.close(() => {
        console.log('[AnyProxy] AnyProxy closed.');
    });
};
process.on('SIGINT', close);
process.on('SIGTERM', close);
