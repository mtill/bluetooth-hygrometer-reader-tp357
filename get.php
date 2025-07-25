<?php

$date = $_REQUEST["date"];
$sensor = $_REQUEST["sensor"];
$thedatadir = "data";


function getContent($sensor, $day, $thedatadir) {
 $result = "";

 $thepath2 = $thedatadir . "/" . $sensor . "/" . $day . ".csv";
 if (file_exists($thepath2)) {
  $result = $result . file_get_contents($thepath2);
 }

 return $result;
}

$date = new DateTime($date);

$fc = getContent($sensor, $date->format("Y-m-d"), $thedatadir);
echo $fc;

?>
