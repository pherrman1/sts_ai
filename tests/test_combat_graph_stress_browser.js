const { chromium } = require(process.env.PLAYWRIGHT_CORE || "playwright-core");
const { pathToFileURL } = require("node:url");
const path = require("node:path");
(async () => {
  const browser=await chromium.launch({executablePath:"/usr/bin/google-chrome",
    headless:true,args:["--no-sandbox","--disable-gpu"]});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    await page.route("http://**/*",route=>route.abort());
    await page.route("https://**/*",route=>route.abort());
    for(const file of process.argv.slice(2)){
      const errors=[];page.on("pageerror",error=>errors.push(error.message));
      const start=Date.now();
      await page.goto(pathToFileURL(path.resolve(file)).href);
      await page.waitForFunction(()=>document.querySelector("#visible-count")?.textContent.includes("retained nodes") &&
        !document.querySelector("#layout-status")?.textContent, {timeout:60000});
      const result=await page.evaluate(()=>({
        visible:document.querySelectorAll("#graph .node").length,
        edges:document.querySelectorAll("#graph .link").length,
        status:document.querySelector("#visible-count").textContent}));
      await page.screenshot({path:"/tmp/"+path.basename(file,".html")+".png"});
      console.log(JSON.stringify({file,elapsedMs:Date.now()-start,...result,errors}));
      if(errors.length || result.visible > 300 || !result.visible)throw Error("bounded view failed");
      if(file.includes("8192")){
        const deeper=Date.now();
        await page.locator("#depth").fill("8");
        await page.locator("#depth").dispatchEvent("change");
        await page.waitForFunction(()=>document.querySelectorAll("#graph .node").length >= 200 &&
          !document.querySelector("#layout-status")?.textContent,{timeout:60000});
        await page.screenshot({path:"/tmp/silver-synthetic-8192-dense.png"});
        console.log(JSON.stringify({file:"dense bounded 8192",elapsedMs:Date.now()-deeper,
          visible:await page.locator("#graph .node").count()}));
      }
    }
    await page.close();
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
