const { createApp } = Vue;

createApp({
  setup() {
    return {
      title: "Test",
    };
  },
  template: `<div><h1>{{ title }}</h1></div>`,
}).mount("#app");
