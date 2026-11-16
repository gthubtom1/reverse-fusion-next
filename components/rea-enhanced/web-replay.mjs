// Owned finite browser replay, inspired by bounded comparison/refinement.
// No Craft code/runtime. Uses the fixed REA package's existing Playwright core.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root, requestPath] = process.argv.slice(2);
const {chromium} = await import(pathToFileURL(path.join(root,'vendor/rea/package/node_modules/playwright-core/index.mjs')));
const request = JSON.parse(fs.readFileSync(requestPath,'utf8'));
const {plan,output,browser:executablePath} = request;
let browser;
let records=[];
try {
  browser = await chromium.launch({headless:true,executablePath});
  for (const width of plan.widths) for (const scenario of plan.scenarios) {
    for (const side of ['original','candidate']) {
      const context = await browser.newContext({viewport:{width,height:800},deviceScaleFactor:1,locale:'en-US',timezoneId:'UTC',reducedMotion:'reduce'});
      const page = await context.newPage();
      page.setDefaultTimeout(5000);
      try {
        await page.goto(plan[side].url,{waitUntil:'domcontentloaded',timeout:15000});
        for (let index=0;index<scenario.steps.length;index++) {
          const step=scenario.steps[index];
          let error=null;
          try {
            if(step.action==='click') await page.locator(step.selector).click();
            else if(step.action==='fill') await page.locator(step.selector).fill(step.value);
            else if(step.action==='press') await page.locator(step.selector).press(step.value);
            else if(step.action==='reload') await page.reload({waitUntil:'domcontentloaded'});
            else if(step.action==='wait') await page.waitForTimeout(step.ms);
            else if(step.action!=='observe') throw new Error('Unsupported action');
          } catch(e) {error=e.message;}
          const observations=[];
          for (const selector of plan.observe) {
            const item=page.locator(selector).first();
            if(!await item.count()) {observations.push({selector,missing:true});continue;}
            observations.push(await item.evaluate((e,selector)=>({selector,text:e.textContent,
              value:['INPUT','TEXTAREA','SELECT'].includes(e.tagName)?e.value:null,
              checked:e.tagName==='INPUT'&&['checkbox','radio'].includes(e.type)?e.checked:null,
              disabled:'disabled' in e?e.disabled:null,
              expanded:e.getAttribute('aria-expanded')}),selector));
          }
          const storage=await page.evaluate(keys=>Object.fromEntries(keys.map(key=>[key,localStorage.getItem(key)])),plan.storage_keys);
          const relative=path.posix.join('screens',scenario.id,String(width),side+'-'+index+'.png');
          const screenshot=path.join(output,...relative.split('/'));
          fs.mkdirSync(path.dirname(screenshot),{recursive:true});
          await page.screenshot({path:screenshot,animations:'disabled',caret:'hide'});
          records.push({scenario:scenario.id,width,side,step:index,error,observations,storage,screenshot:relative});
          if(error) break;
        }
      } catch(e) {records.push({scenario:scenario.id,width,side,step:0,error:e.message,observations:[],storage:{},screenshot:null});}
      finally {await context.close();}
    }
  }
  process.stdout.write(JSON.stringify({records}));
} catch(e) {
  process.stdout.write(JSON.stringify({records,error:e.message}));
  process.exitCode=2;
} finally {if(browser) await browser.close();}
