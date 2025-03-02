var express = require('express');
var router = express.Router();

/* GET home page. */
router.get('/', async (req, res, next) => {
  res.render('ejs/pages/devices', { title: 'Devices' });
});

module.exports = router;
