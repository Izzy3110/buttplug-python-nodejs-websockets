var createError = require("http-errors");
var express = require("express");

var path = require("path");
var cookieParser = require("cookie-parser");
var logger = require("morgan");

require("dotenv").config();

var indexRouter = require("./routes/index");
var devicesRouter = require("./routes/devices");
var aboutRouter = require("./routes/about");

var app = express();

// view engine setup
app.set('view engine', 'ejs');
app.set("views", path.join(__dirname, "views"));

app.use(logger("dev"));
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
app.use(cookieParser());
app.use(express.static(path.join(__dirname, "public")));


app.use('/styles', express.static(path.join(__dirname, 'static', 'styles')));

app.use('/images', express.static(path.join(__dirname, 'static', 'images')));

app.use('/jquery-circle-progress', express.static(path.join(__dirname, 'node_modules', 'jquery-circle-progress')));


if (process.env.NODE_ENV === "development") {
  var livereload = require("livereload");
  var connectLiveReload = require("connect-livereload");

  const liveReloadServer = livereload.createServer();
  liveReloadServer.watch(path.join(__dirname, "public"));
  liveReloadServer.server.once("connection", () => {
    setTimeout(() => {
      liveReloadServer.refresh("/");
    }, 100);
  });
  app.use(connectLiveReload());
}

app.use("/", indexRouter);
app.use("/devices", devicesRouter);
app.use("/about", aboutRouter);

// catch 404 and forward to error handler
app.use(function (req, res, next) {
  next(createError(404));
});

// error handler
app.use(async (err, req, res, next) => {
  // set locals, only providing error in development
  res.locals.message = err.message;
  res.locals.error = req.app.get("env") === "development" ? err : {};

  // render the error page
  res.status(err.status || 500);
  res.render("ejs/pages/error", {title: "Hey! An error occured :(", error_message: err.message});
});

// WebSocket Handler Function
const WebSocket = require('ws');



function handleWebSocket(server) {
  const wss = new WebSocket.Server({ server });
  // Array to store all connected WebSocket clients
  const clients = [];


  wss.on('connection', (ws) => {
    console.log('New WebSocket connection established.');
    ws.send(JSON.stringify({devices: []}))

    // Add the new client to the clients array
    clients.push(ws);

    

    // Handle messages from the client
    ws.on('message', (message) => {
      console.log('Received message: ', message.toString());
      // mqtt_client.publish("/nodejs/mqtt", message.toString())
      // mqtt_client.publish(process.env.MQTT_TOPIC, message.toString())
      // console.log(clients.length)
      clients.forEach(client => {
        // Send the message to each client except the sender
        if (client !== ws && client.readyState === WebSocket.OPEN) {
          client.send(message.toString());
        }
        
      });
    });

    // Handle WebSocket connection close
    ws.on('close', () => {
      console.log('WebSocket connection closed');
    });
  });
}

module.exports = { app, handleWebSocket };
