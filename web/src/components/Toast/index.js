import { createVNode, render } from 'vue'
import ToastComponent from './Index.vue'

// 模块级单例：Toast 挂载在 document.body 下，与 Vue 组件树独立。
// 优点是调用方无需在 template 中声明组件即可使用。
// 缺点是不共享 App 的 provide/inject——当前场景下无此需求，可接受。
const div = document.createElement('div')
document.body.appendChild(div)

const vnode = createVNode(ToastComponent)
render(vnode, div)

// 向外暴露符合开发者直觉的全局快捷对象
export const toast = {
  info(msg, duration) {
    vnode.component.exposed.add(msg, 'info', duration)
  },
  success(msg, duration) {
    vnode.component.exposed.add(msg, 'success', duration)
  },
  warning(msg, duration) {
    vnode.component.exposed.add(msg, 'warning', duration)
  },
  error(msg, duration) {
    vnode.component.exposed.add(msg, 'error', duration)
  },
}