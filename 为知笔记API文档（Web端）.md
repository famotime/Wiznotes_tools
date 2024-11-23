# 为知笔记API文档（Web端）
https://www.wiz.cn/wapp/pages/book/bb8f0f10-48ca-11ea-b27a-ef51fb9d4bb4/700c0ba0-48cb-11ea-a61a-d3d58d67def9

## 为知笔记API快速上手
### 主要架构
为知笔记服务主要分为两部分：

1. 账号服务
2. 数据服务

其中账号服务（as: Account Server）只有一个服务地址，主要提供账号相关的服务，例如登录，注销，获取用户信息，获取用户数据信息等。
一个账号可以有一个或者多个知识库（kb: Knowledge Base），每一个kb都是独立的。每一个kb，数据都保存在某一个数据服务上面。
数据服务（ks: Knowledge Server）可能有多个，每一个数据服务都包含若干kb，提供数据的读写服务。

### 登录
可以使用用户名密码直接登录，如果登录正常，服务器将返回用户个人kb，token等信息。

```javascript
const axios = require('axios');
const AS_URL = 'https://as.wiz.cn';
async function execRequest(method, url, body, token) {
  const options = {
    url,
    method,
    data: body,
  };
  if (token) {
    options.headers = {
      'X-Wiz-Token': token,
    };
  }
  const res = await axios(options);
  const data = res.data;
  if (data.returnCode !== 200) {
    console.error(`request error: ${data.returnMessage}`);
    const err = new Error(data.returnMessage);
    err.code = data.returnCode;
    err.externCode = data.externCode;
    throw err;
  }
  return data.result;
}
async function login(userId, password) {
  return await execRequest('post', `${AS_URL}/as/user/login`, {userId, password});
}
async function getFolders(kbServer, kbGuid, token) {
  return await execRequest('get', `${kbServer}/ks/category/all/${kbGuid}`, null, token);
}
async function test() {
  const userId = 'test_api@wiz.cn';
  const password = '123456';
  try {
    const loginResult = await login(userId, password);
    console.log(JSON.stringify(loginResult, null, 2));
  } catch (err) {
    if (err.externCode === 'WizErrorInvalidPassword') {
      console.error('Invalid password');
    } else {
      console.error(err.message);
    }
  }
}
test();
```
### 获取个人笔记文件夹列表
用户登录返回的信息里面，包含kb服务器地址：（kbServer）, kbGuid，我们可以利用这两个参数，向ks发送请求获取相应的数据：

```javascript
async function getFolders(kbServer, kbGuid, token) {
  return await execRequest('get', `${kbServer}/ks/category/all/${kbGuid}`, null, token);
}
async function test() {
  const userId = 'test_api@wiz.cn';
  const password = '123456';
  try {
    const loginResult = await login(userId, password);
    console.log(JSON.stringify(loginResult, null, 2));
    //
    const {kbServer, kbGuid, token} = loginResult;
    const folders = await getFolders(kbServer, kbGuid, token);
    console.log(JSON.stringify(folders, null, 2));
    //
  } catch (err) {
    if (err.externCode === 'WizErrorInvalidPassword') {
      console.error('Invalid password');
    } else {
      console.error(err.message);
    }
  }
}
```
### 获取文件夹下面的笔记
```javascript
async function getFolderNotes(kbServer, kbGuid, folder, token) {
  const count = 50;
  let start = 0;
  let notes = [];
  folder = encodeURIComponent(folder);
  for (;;) {
    let params = `start=${start}&count=${count}&category=${folder}&orderBy=created`;
    let subNotes = await execRequest('get', `${kbServer}/ks/note/list/category/${kbGuid}?${params}`, null, token);
    notes = notes.concat(subNotes);
    start += count;
    if (subNotes.length < count) {
      break;
    }
  }
  return notes;
}
async function test() {
  const userId = 'test_api@wiz.cn';
  const password = '123456';
  try {
    const loginResult = await login(userId, password);
    console.log(JSON.stringify(loginResult, null, 2));
    //
    const {kbServer, kbGuid, token} = loginResult;
    const folders = await getFolders(kbServer, kbGuid, token);
    console.log(JSON.stringify(folders, null, 2));
    //
    for (let folder of folders) {
      const notes = await getFolderNotes(kbServer, kbGuid, folder, token);
      console.log(JSON.stringify(notes, null, 2));
    }
    //
  } catch (err) {
    if (err.externCode === 'WizErrorInvalidPassword') {
      console.error('Invalid password');
    } else {
      console.error(err.message);
    }
  }
}
```
### 创建文件夹
```javascript
async function createFolder(kbServer, kbGuid, parent, child, token) {
  const body = {
    parent,
    child,
  };
  return await execRequest('post', `${kbServer}/ks/category/create/${kbGuid}`, body, token);
}
async function test() {
  const userId = 'test_api@wiz.cn';
  const password = '123456';
  try {
    const loginResult = await login(userId, password);
    console.log(JSON.stringify(loginResult, null, 2));
    //
    const {kbServer, kbGuid, token} = loginResult;
    const folders = await getFolders(kbServer, kbGuid, token);
    console.log(JSON.stringify(folders, null, 2));
    //
    for (let folder of folders) {
      const notes = await getFolderNotes(kbServer, kbGuid, folder, token);
      console.log(JSON.stringify(notes, null, 2));
    }
    //
    await createFolder(kbServer, kbGuid, '/', 'My Folder 1', token);
    await createFolder(kbServer, kbGuid, '/', 'My Folder 2', token);
    await createFolder(kbServer, kbGuid, '/My Folder 1/', 'My Sub Folder 1', token);
    await createFolder(kbServer, kbGuid, '/My Folder 1/', 'My Sub Folder 2', token);
    //
    const folders2 = await getFolders(kbServer, kbGuid, token);
    console.log(JSON.stringify(folders2, null, 2));
    //
  } catch (err) {
    if (err.externCode === 'WizErrorInvalidPassword') {
      console.error('Invalid password');
    } else {
      console.error(err.message);
    }
  }
}
```
### 新建笔记
```javascript
async function createNote(kbServer, kbGuid, title, folder, html, extOptions, token) {
  const url = `${kbServer}/ks/note/create/${kbGuid}`;
  let note = {
    kbGuid,
    title,
    category: folder,
    html,
  };
  //
  if (extOptions) {
    note = Object.assign(note, extOptions);
  }
  //
  return await execRequest('post', url, note, token);
}
const noteHtml = `
<!doctype html>
<html>
  <head>
    <title>Note from API</title>
  </head>
  <body>
    <p>Hello WizNote</p>
  </body>
</html>`;
async function test() {
  const userId = 'test_api@wiz.cn';
  const password = '123456';
  try {
    const loginResult = await login(userId, password);
    console.log(JSON.stringify(loginResult, null, 2));
    //
    const {kbServer, kbGuid, token} = loginResult;
    const folders = await getFolders(kbServer, kbGuid, token);
    console.log(JSON.stringify(folders, null, 2));
    //
    for (let folder of folders) {
      const notes = await getFolderNotes(kbServer, kbGuid, folder, token);
      console.log(JSON.stringify(notes, null, 2));
    }
    //
    await createFolder(kbServer, kbGuid, '/', 'My Folder 1', token);
    await createFolder(kbServer, kbGuid, '/', 'My Folder 2', token);
    await createFolder(kbServer, kbGuid, '/My Folder 1/', 'My Sub Folder 1', token);
    await createFolder(kbServer, kbGuid, '/My Folder 1/', 'My Sub Folder 2', token);
    //
    const folders2 = await getFolders(kbServer, kbGuid, token);
    console.log(JSON.stringify(folders2, null, 2));
    //
    const newNote1 = await createNote(kbServer, kbGuid, 'Hello WizNote', '/My Folder 1/', noteHtml, null, token);
    console.log(JSON.stringify(newNote1, null, 2));
    //
  } catch (err) {
    if (err.externCode === 'WizErrorInvalidPassword') {
      console.error('Invalid password');
    } else {
      console.error(err.message);
    }
  }
}
```
运行之后的结果：

![image](images/0.8347240442383411.png)

## 为知笔记API调用约定
### 判断请求是否成功
如果发生http错误，通常都是网络问题，也可能是为知笔记服务端没有正常启动等。具体请查看网络或者服务端日志。

如果没有发生http错误，除非特别说明，否则请求和返回的数据，都是json格式。

为知笔记API返回的数据，除非特别说明，格式如下：

```javascript
{
    returnCode: 200,
    returnMessage: "OK",
    externCode: "",
    result: xxx
}
```
如果请求成功，则returnCode=200。
请求成功后，如果有返回结果，请求结果在result字段。result可能是一个值，也可能是一个对象。

所有不等于200的returnCode值，都表示请求失败。具体失败原因，可以参考returnMessage以及externCode。
externCode对于特定的失败原因会返回特定的值，可以用来区分错误原因。
returnMessage则是可阅读的错误提示，同样的错误也可能返回不同的内容，不要用来区分错误原因。

### url里面的参数，包含路径参数以及query string参数
例如下面的url里面就包含参数，参数统一用:paramName表示，例如:bizGuid代表一个团队的Guid，请使用bizGuid的值替换

```javascript
get /as/biz/user_kb_list?bizGuid=:bizGuid
get /as/user/avatar/:userGuid
get /ks/note/download/:kbGuid/:docGuid?downloadInfo=true|false&=downloadData=true|false
```
如果参数是可选值，例如downloadInfo=true|false，代表downloadInfo只有两种参数可选，分别是true或者false。

### body参数
例如注册用户，则需要通过json提交userId， password两个参数

```javascript
post /as/user/signup
body: {
  userId,
  password,
}
```
### 常见错误代码
#### returnCode可能的返回值如下：
* 200: 请求成功
* 301: 无效的token或者没有token
* 31002：密码错误
* 2000: 参数错误，通常是缺少参数，或者参数错误
* 2001：内部错误，通常是服务端遇到无法出路的错误，或者未知错误
* 2002：OSS错误，数据存储错误
* 2003：逻辑错误，例如数据错误等
* 2004：数据不存在错误
* 2005：禁止访问，通常是用户权限问题
* 2006：解压缩错误，通常是数据错误
* 2007：上传限制错误，通常代表用户vip可能过期等
* 2009：OAUTH错误，OAuth功能出错

#### externCode错误格式：
通常以WizError开头，例如：

* WizErrorServiceExpired：团队服务到期
* WizErrorUserNotExists：用户不存在
* WizErrorInvalidPassword：密码错误
具体错误，请参考具体的API请求。

## 为知笔记API token传递方式
调用为知笔记API的时候，除了用户注册等少数API，其他的API都需要用户token。token必须通过http请求的head传递，head key为X-Wiz-Token。

下面是一个例子：

```javascript
async function execRequest(method, url, body, token) {
  const options = {
    url,
    method,
    data: body,
  };
  if (token) {
    options.headers = {
      'X-Wiz-Token': token,
    };
  }
  const res = await axios(options);
  const data = res.data;
  if (data.returnCode !== 200) {
    console.error(`request error: ${data.returnMessage}`);
    const err = new Error(data.returnMessage);
    err.code = data.returnCode;
    err.externCode = data.externCode;
    throw err;
  }
  return data.result;
}
```
## 创建图文笔记
为知笔记里面的笔记，都是标准的html格式。因此您可以按照html语法插入外部图片。但是外部图片并不是十分可靠，有可能失效从而导致图片无法显示。要解决这个问题，您可以将笔记里面的图片作为资源保存到笔记里面，然后在html里面引用，这样就可以避免图片丢失的问题。

### 第一步，创建一个空的笔记
首先我们需要有一个笔记，然后再向这个笔记添加资源，最后，根据添加的资源，修改笔记html，完成图文笔记。

```javascript
  //create an empty note
  const note = await createNote(kbServer, kbGuid, 'Hello WizNote (with image)', folder, '<html><head></head><body></body></html>', null, token);
```
### 第二步，上传图片
```javascript
//注意：axios 0.15.2-0.15.3版本有bug，请升级到最新版本，否则上传文件会报错
//
async function uploadImage(kbServer, kbGuid, docGuid, imageFile, token) {
  //
  const url = `${kbServer}/ks/resource/upload/${kbGuid}/${docGuid}`;
  //
  const formData = new FormData();
  formData.append('kbGuid', kbGuid);
  formData.append('docGuid', docGuid);
  formData.append('data', fs.createReadStream(imageFile), {
    filename: path.basename(imageFile),
  });
  //
  const headers = {
    ...formData.getHeaders(),
  };
  //
  return await execRequest('post', url, formData, token, headers);
}

...

  const home = process.env.HOME;
  const imageFile1 = path.resolve(home, 'test1.jpg');
  const image1 = await uploadImage(kbServer, kbGuid, docGuid, imageFile1, token);
  const imageFile2 = path.resolve(home, 'test2.jpg');
  const image2 = await uploadImage(kbServer, kbGuid, docGuid, imageFile2, token);
```
### 第三步，修改笔记内容，显示图片
```javascript
async function updateNote(kbServer, kbGuid, note, token) {

  const docGuid = note.docGuid;
  const url = `${kbServer}/ks/note/save/${kbGuid}/${docGuid}`;
  //
  return await execRequest('put', url, note, token);
}

  let htmlWithImage = `<html><body><p>image 1 <br /><img src='${image1.url}' /><br />image 2<br /><img src='${image2.url}' /></p></body></html>`;
  let resources = [image1.name, image2.name];
  //
  note.html = htmlWithImage;
  note.resources = resources;
  //
  await updateNote(kbServer, kbGuid, note, token);
```
### 完整代码
```javascript
const axios = require('axios');
const FormData = require('form-data');
const path = require('path');
const fs = require('fs');

const AS_URL = 'https://as.wiz.cn';

async function execRequest(method, url, body, token, headers) {
  const options = {
    url,
    method,
    data: body,
  };
  if (token) {
    options.headers = {
      'X-Wiz-Token': token,
    };
  }
  if (headers) {
    options.headers = Object.assign({}, options.headers || {}, headers);
  }
  //
  const res = await axios(options);
  const data = res.data;
  if (data.returnCode !== 200) {
    console.error(`request error: ${data.returnMessage}`);
    const err = new Error(data.returnMessage);
    err.code = data.returnCode;
    err.externCode = data.externCode;
    throw err;
  }
  return data.result;
}

async function login(userId, password) {
  return await execRequest('post', `${AS_URL}/as/user/login`, {userId, password});
}

async function createNote(kbServer, kbGuid, title, folder, html, extOptions, token) {

  const url = `${kbServer}/ks/note/create/${kbGuid}`;
  let note = {
    kbGuid,
    title,
    category: folder,
    html,
  };
  //
  if (extOptions) {
    note = Object.assign(note, extOptions);
  }
  //
  //
  return await execRequest('post', url, note, token);
}
//

async function updateNote(kbServer, kbGuid, note, token) {

  const docGuid = note.docGuid;
  const url = `${kbServer}/ks/note/save/${kbGuid}/${docGuid}`;
  //
  return await execRequest('put', url, note, token);
}
//
//
//注意：axios 0.15.2-0.15.3版本有bug，请升级到最新版本，否则上传文件会报错
//
async function uploadImage(kbServer, kbGuid, docGuid, imageFile, token) {
  //
  const url = `${kbServer}/ks/resource/upload/${kbGuid}/${docGuid}`;
  //
  const formData = new FormData();
  formData.append('kbGuid', kbGuid);
  formData.append('docGuid', docGuid);
  formData.append('data', fs.createReadStream(imageFile), {
    filename: path.basename(imageFile),
  });
  //
  const headers = {
    ...formData.getHeaders(),
  };
  //
  return await execRequest('post', url, formData, token, headers);
}

async function createNoteWithImage(kbServer, kbGuid, folder, token) {
  //create an empty note
  const note = await createNote(kbServer, kbGuid, 'Hello WizNote (with image)', folder, '<html><head></head><body></body></html>', null, token);
  //
  const docGuid = note.docGuid;
  //
  const home = process.env.HOME;
  const imageFile1 = path.resolve(home, 'test1.jpg');
  const image1 = await uploadImage(kbServer, kbGuid, docGuid, imageFile1, token);
  const imageFile2 = path.resolve(home, 'test2.jpg');
  const image2 = await uploadImage(kbServer, kbGuid, docGuid, imageFile2, token);
  //
  let htmlWithImage = `<html><body><p>image 1 <br /><img src='${image1.url}' /><br />image 2<br /><img src='${image2.url}' /></p></body></html>`;
  let resources = [image1.name, image2.name];
  //
  note.html = htmlWithImage;
  note.resources = resources;
  //
  await updateNote(kbServer, kbGuid, note, token);
  //
  return note;
}

async function test() {
  const userId = 'test_api@wiz.cn';
  const password = '123456';
  try {
    const loginResult = await login(userId, password);
    console.log(JSON.stringify(loginResult, null, 2));
    //
    const {kbServer, kbGuid, token} = loginResult;
    //
    const note = await createNoteWithImage(kbServer, kbGuid, '/My Notes/', token);
    console.log(JSON.stringify(note, null, 2));
    //
  } catch (err) {
    if (err.externCode === 'WizErrorInvalidPassword') {
      console.error('Invalid password');
    } else {
      console.error(err.message);
    }
  }
}

test();
```
执行代码后的结果：

![image](images/733b70aa-6232-4372-9195-c14bf0df8dfb.jpeg)



## 创建markdown笔记
在为知笔记里面，markdown笔记和普通笔记没有什么区别，只是在笔记标题后面增加了.md结尾，标记笔记是markdown格式。笔记内容，仍然是一个标准的html文件。在显示笔记的时候，会首先从html里面提取纯文本，然后按照markdown语法，将纯文本按照markdown语法，重新渲染成html，然后显示。

为了方便插入图片，为知笔记对插入图片功能做了优化，用户可以在编辑器里面，直接按照普通笔记方式插入图片（或者使用剪贴板直接粘贴剪贴板里面的图片），并且这个图片可以在编辑器內直接显示出来，而不是像markdown那样，显示为语法。

下面的代码，同时采用这两种方式，在markdown里面显示图片。如果您的笔记还需要在为知笔记里面编辑，那么建议您按照普通笔记方式插入和显示图片。

```javascript
const axios = require('axios');
const FormData = require('form-data');
const path = require('path');
const fs = require('fs');

const AS_URL = 'https://as.wiz.cn';

async function execRequest(method, url, body, token, headers) {
  const options = {
    url,
    method,
    data: body,
  };
  if (token) {
    options.headers = {
      'X-Wiz-Token': token,
    };
  }
  if (headers) {
    options.headers = Object.assign({}, options.headers || {}, headers);
  }
  //
  const res = await axios(options);
  const data = res.data;
  if (data.returnCode !== 200) {
    console.error(`request error: ${data.returnMessage}`);
    const err = new Error(data.returnMessage);
    err.code = data.returnCode;
    err.externCode = data.externCode;
    throw err;
  }
  return data.result;
}

async function login(userId, password) {
  return await execRequest('post', `${AS_URL}/as/user/login`, {userId, password});
}

async function createNote(kbServer, kbGuid, title, folder, html, extOptions, token) {

  const url = `${kbServer}/ks/note/create/${kbGuid}`;
  let note = {
    kbGuid,
    title,
    category: folder,
    html,
  };
  //
  if (extOptions) {
    note = Object.assign(note, extOptions);
  }
  //
  //
  return await execRequest('post', url, note, token);
}
//

async function updateNote(kbServer, kbGuid, note, token) {

  const docGuid = note.docGuid;
  const url = `${kbServer}/ks/note/save/${kbGuid}/${docGuid}`;
  //
  return await execRequest('put', url, note, token);
}
//
//
//注意：axios 0.15.2-0.15.3版本有bug，请升级到最新版本，否则上传文件会报错
//
async function uploadImage(kbServer, kbGuid, docGuid, imageFile, token) {
  //
  const url = `${kbServer}/ks/resource/upload/${kbGuid}/${docGuid}`;
  //
  const formData = new FormData();
  formData.append('kbGuid', kbGuid);
  formData.append('docGuid', docGuid);
  formData.append('data', fs.createReadStream(imageFile), {
    filename: path.basename(imageFile),
  });
  //
  const headers = {
    ...formData.getHeaders(),
  };
  //
  return await execRequest('post', url, formData, token, headers);
}

async function createNoteWithImage(kbServer, kbGuid, folder, token) {
  //create an empty note
  const note = await createNote(kbServer, kbGuid, 'Hello Markdown.md', folder, '<html><head></head><body></body></html>', null, token);
  //
  const docGuid = note.docGuid;
  //
  const home = process.env.HOME;
  const imageFile1 = path.resolve(home, 'test1.jpg');
  const image1 = await uploadImage(kbServer, kbGuid, docGuid, imageFile1, token);
  const imageFile2 = path.resolve(home, 'test2.jpg');
  const image2 = await uploadImage(kbServer, kbGuid, docGuid, imageFile2, token);
  //
  let htmlWithImage = `<html><body>
<pre>
# markdown head 1

1. list 1
1. list 2
1. list 3

* item 1
* item 2
* item 2

image 1
![](${image1.url})

image 2
![](${image2.url})

</pre>

<div>## insert image with html</div>

<div><img src='${image1.url}' /></div>

</body></html>`;
  let resources = [image1.name, image2.name];
  //
  note.html = htmlWithImage;
  note.resources = resources;
  //
  await updateNote(kbServer, kbGuid, note, token);
  //
  return note;
}

async function test() {
  const userId = 'test_api@wiz.cn';
  const password = '123456';
  try {
    const loginResult = await login(userId, password);
    console.log(JSON.stringify(loginResult, null, 2));
    //
    const {kbServer, kbGuid, token} = loginResult;
    //
    const note = await createNoteWithImage(kbServer, kbGuid, '/My Notes/', token);
    console.log(JSON.stringify(note, null, 2));
    //
  } catch (err) {
    if (err.externCode === 'WizErrorInvalidPassword') {
      console.error('Invalid password');
    } else {
      console.error(err.message);
    }
  }
}

test();
```
代码执行效果：

![image](images/b406e937-6c46-46e1-989d-829a63fc961b.jpeg)



## 登录/注册相关
### 用户登录
```javascript
post /as/user/login
body: {
  userId,
  password,
}
```
### 通过有效的token，获取用户信息
```javascript
post /as/user/login/token
body: {
  token
}
```
### 注销token
```javascript
get /as/user/logout
```
### 延长token有效期
```javascript
get /as/user/keep
```
### 获取用户信息
```javascript
get /as/user/info
```
### 通过当前token获取一个临时id
然后通过这个id，在60秒内可以重新拿到token。该id一次有效，使用后就会失效。

```javascript
get /as/token/token2temp
```
可以用于跨域页面跳转，避免泄漏token

### 通过tokenid获取token
```javascript
get /as/token/temp2token?tempToken=:tempToken
```
## 笔记相关
### 下载笔记
```javascript
get /ks/note/download/:kbGuid/:docGuid?downloadInfo=1|0&=downloadData=1|0
```
### 新建笔记，用于web新建笔记
```javascript
post /ks/note/create/:kbGuid
body: {
  kbGuid,
  html,
  title,
  category, //example: /My Notes/
}
```
### 保存笔记html
```javascript
put /ks/note/save/:kbGuid/:docGuid
body: {
  kbGuid,
  docGuid,
  html,
  url,
  tags, //tagGuid1*tagGuid2
  author,
  keywords,
  resources, //[a.png, 1.jpg] 需要上传笔记包含的所有资源文件，服务端会返回需要上传的resource
}
```
### 上传一个图片
```javascript
post /ks/resource/upload/:kbGuid/:docGuid
content-type: multipart/form-data
body: {
  kbGuid,
  docGuid,
  data, //resource file
}
```
### 获取笔记图片缩略图，如果不存在报告404
```javascript
get /ks/note/abstract/:kbGuid/:docGuid
```
### 下载加密笔记数据，笔记资源，附件数据， 笔记缩略图
```javascript
get /ks/object/download/:kbGuid/:docGuid?objType=document
```
### 下载附件数据
get /ks/object/download/:kbGuid/:docGuid?objId=:attGuid&objType=attachment

```javascript
### 下载笔记资源数据
get /ks/object/download/:kbGuid/:docGuid?objId=:resName&objType=resource
```
### 获取笔记/附件历史版本列表
```javascript
get /ks/history/list/:kbGuid/:docGuid?objType=document|attachment&objGuid=docGuid|attGuid
```
### 获取某一个文件夹下面的笔记列表
通过start和count进行分页获取。

```javascript
get /ks/note/list/category/:kbGuid?category=:folder&withAbstract=true|false&start=:start&count=:count&orderBy=title|created|modified&ascending=asc|desc
```
### 获取某一个标签下面的笔记列表
```javascript
get /ks/note/list/tag/:kbGuid?tag=:tagGuid&withAbstract=true|false&start=:start&count=:count&orderBy=title|created|modified&ascending=asc|desc
```
### 获取某一个笔记的附件列表
```javascript
get /ks/note/attachments/:kbGuid/:docGuid
```
### 删除笔记
```javascript
delete /ks/note/delete/:kbGuid/:docGuid/
```
### 获取某一个笔记资源数据，用于直接在浏览器内显示笔记内容
```javascript
get /ks/note/view/:kbGuid/:docGuid/images/:resName
```
### 获取笔记html，用户在浏览器内直接显示笔记
```javascript
get /ks/note/view/:kbGuid/:docGuid/
```
### 获取笔记信息
```javascript
get /ks/note/info/:kbGuid/:docGuid
```
## 附件相关
### 创建一个附件
```javascript
post /ks/attachment/create/:kbGuid/:docGuid
content-type: multipart/form-data
body: {
  kbGuid,
  docGuid,
  data, //http file data
}
```
### 下载附件。直接返回附件的数据流
```javascript
get /ks/attachment/download/:kbGuid/:docGuid/:attGuid
```
### 删除一个附件
```javascript
delete /ks/attachment/delete/:kbGuid/:docGuid/:attGuid
```


## 个人笔记文件夹
### 获取所有文件夹
```javascript
get /ks/category/all/:kbGuid
```
### 创建文件夹
```javascript
post /ks/category/create/:kbGuid
body: {
  parent, //example: /My Notes/
  child, //example: new folder
  pos, //timestamp
}
```
### 排序文件夹
```javascript
put /ks/category/sort/:kbGuid
body: {
  '/My Notes/': 0,
  '/New Folder/': 1,
}
```
### 重命名文件夹
```javascript
put /ks/category/rename/:kbGuid
body: {
  from, // example: /My Notes/New folder/
  to: // exapmel: My folder
}
```
### 删除文件夹
```javascript
delete /ks/category/delete/:kbGuid
```


## 个人笔记标签 / 群组目录相关
**群组目录采用标签实现，对于群组里面的目录，就是群组的标签**

### 获取全部标签
```javascript
get /ks/tag/all/:kbGuid
```
### 创建标签
```javascript
post /ks/tag/create/:kbGuid
body: {
  parentTagGuid,
  name,
}
```
### 重命名标签
```javascript
put /ks/tag/rename/:kbGuid
body: {
  tagGuid,
  name,
}
```
### 移动标签
```javascript
put /ks/tag/move/:kbGuid
body: {
  tagGuid,
  parentTagGuid,
}
```
### 删除标签
```javascript
delete /ks/tag/delete/:kbGuid/:tagGuid
```
## 搜索笔记
### 搜索笔记
```javascript
get /ks/note/search/:kbGuid?ss=:searchText
```


## kb相关
### 获取kb信息
```javascript
get /ks/kb/info/:kbGuid
```
### 获取某一个kb的笔记数量
```javascript
get /ks/kb/:kbGuid/document/count
```
