const express = require("express");

const {createServer} = require("http");
const {WebSocketServer} = require("ws");

const app = express();

app.use(express.static("public"));

const server = createServer(app);

const wss = new WebSocketServer({ server });
const websocket = require('ws');
const fs = require('fs');
const ws = new websocket('wss://api.alphacephei.com/asr/en/');

ws.on('open', function open() {
    var readStream = fs.createReadStream('test16k.wav');
    readStream.on('data', function (chunk) {
        ws.send(chunk);
    });
    readStream.on('end', function () {
        ws.send('{"eof" : 1}');
    });
});

ws.on('message', function incoming(data) {
    console.log(data);
});

ws.on('close', function close() {
    process.exit()
});


let clients = [];

function serverStart() {
    let port = this.address().port;
    console.log("Server listening on port " + port);
}

function handleClient(thisClient, request) {
    console.log("New Connection");

    clients.push(thisClient);

    function endClient() {
        // when a client closes its connection
        // get the client's position in the array
        // and delete it from the array:
        let position = clients.indexOf(thisClient);
        clients.splice(position, 1);
        console.log("connection closed");
    }

    // if a client sends a message, print it out:
    function clientResponse(data) {
        console.log(`received from client: ${data.toString()}`);
        broadcast(data.toString());
    }

    // This function broadcasts messages to all webSocket clients
    function broadcast(data) {
        // iterate over the array of clients & send data to each
        for (let c in clients) {
            clients[c].send(data);
        }
    }

    // set up client event listeners:
    thisClient.on("message", clientResponse);
    thisClient.on("close", endClient);
}

// start the server:
server.listen(process.env.PORT || 3000, serverStart);

// start the websocket server listening for clients:
wss.on("connection", handleClient);
