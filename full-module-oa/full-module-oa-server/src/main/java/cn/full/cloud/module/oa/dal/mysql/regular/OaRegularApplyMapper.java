package cn.full.cloud.module.oa.dal.mysql.regular;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.oa.controller.admin.regular.vo.OaRegularApplyPageReqVO;
import cn.full.cloud.module.oa.dal.dataobject.regular.OaRegularApplyDO;
import org.apache.ibatis.annotations.Mapper;

/**
 * OA 转正申请 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface OaRegularApplyMapper extends BaseMapperX<OaRegularApplyDO> {

    default PageResult<OaRegularApplyDO> selectPage(Long userId, OaRegularApplyPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<OaRegularApplyDO>()
                .eq(OaRegularApplyDO::getCreator, userId.toString())
                .likeIfPresent(OaRegularApplyDO::getTitle, reqVO.getTitle())
                .eqIfPresent(OaRegularApplyDO::getStatus, reqVO.getStatus())
                .orderByDesc(OaRegularApplyDO::getCreateTime, OaRegularApplyDO::getId));
    }

}
