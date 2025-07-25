// url, method, (isAsynchronous), (data), (contentType), (responseType), (successFunction), (failFunction)
function doAjax(paramMap) {
    var therequest = new XMLHttpRequest();
    if (paramMap.hasOwnProperty("responseType")) {
        therequest.responseType = paramMap.responseType;
    }
    therequest.onreadystatechange = function() {
        if (this.readyState == 4 && this.status == 200) {
            if (paramMap.hasOwnProperty("successFunction")) {
                paramMap.successFunction(therequest);
            }
        } else {
            if (paramMap.hasOwnProperty("failFunction")) {
                paramMap.failFunction(therequest);
            }
        }
    }
    var isAsynchronous = true;
    if (paramMap.hasOwnProperty("isAsynchronous")) {
        isAsynchronous = paramMap.isAsynchronous;
    }
    var themethod = "GET";
    if (paramMap.hasOwnProperty("method")) {
        themethod = paramMap.method;
    }
    therequest.open(themethod, paramMap.url, isAsynchronous);
    if (paramMap.hasOwnProperty("contentType")) {
        therequest.setRequestHeader('Content-Type', paramMap.contentType);
    }
    if (paramMap.hasOwnProperty("data")) {
        therequest.send(paramMap.data);
    } else {
        therequest.send();
    }
}

